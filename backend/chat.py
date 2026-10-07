"""Assistant conversationnel ("call") : recherche rapide puis approfondie dans le wiki.

Déroulé d'une question :
  1. Recherche rapide : index plein texte sur la question, les meilleures pages
     sont injectées directement dans le contexte du modèle.
  2. Recherche approfondie : si ça ne suffit pas, le modèle appelle lui-même les
     outils `search_docs` / `read_doc` (si le modèle supporte le tool calling).
  3. La réponse est streamée token par token (le frontend la lit à voix haute).

Toutes les étapes sont émises sous forme d'événements (dict) pour que l'UI
affiche en direct ce que l'IA est en train de fouiller.
"""
import json
import logging
from typing import AsyncIterator, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

FAST_RESULTS     = 3      # pages injectées d'office dans le contexte
PAGE_CHARS       = 3000   # taille max d'une page injectée / lue
MAX_TOOL_ROUNDS  = 4      # nombre max d'aller-retours outils
HISTORY_MESSAGES = 10     # messages d'historique transmis au modèle


class ToolsUnsupported(Exception):
    """Le modèle Ollama ne supporte pas le tool calling (ex: phi)."""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Recherche plein texte dans la base de connaissances IT. "
                "Utilise des mots-clés techniques précis ou le symptôme / message d'erreur, "
                "essaie des synonymes si la première recherche ne donne rien (ex: 'forticlient 98%', 'spooler')."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Mots-clés à chercher"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": "Lit le contenu complet d'une page de la base de connaissances.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string", "description": "Nom de fichier renvoyé par search_docs"}},
                "required": ["filename"],
            },
        },
    },
]

BASE_PROMPT = """Tu es l'assistant ops d'une équipe de techniciens IT. Un technicien te pose une question pendant une intervention.
Réponds en français, UNIQUEMENT à partir de la base de connaissances. N'invente jamais de procédure, d'adresse ou de commande.
Si l'information n'est pas dans la base, dis-le clairement en une phrase.

La base contient surtout des STORIES d'incidents (Symptômes → Diagnostic → Résolution → Vérification).
- Vérifie d'abord que les symptômes décrits par le technicien correspondent à ceux de la story.
  S'ils ne correspondent qu'en partie, dis-le et propose la vérification de diagnostic qui permet de trancher.
- Donne ensuite la résolution dans l'ordre, puis la vérification à faire.
- Si plusieurs stories peuvent correspondre, pose UNE question courte pour les départager."""

TOOLS_PROMPT = """Si les pages ci-dessous ne suffisent pas, utilise l'outil search_docs avec d'autres mots-clés
(synonymes, nom du logiciel, message d'erreur…) puis read_doc pour lire une page en entier.
Ne fais pas de recherche si les pages fournies répondent déjà à la question."""

VOICE_PROMPT = """Ta réponse sera LUE À VOIX HAUTE au technicien : 2 à 5 phrases courtes et directes,
pas de Markdown, pas de listes à puces, pas de tableaux. Énonce les étapes dans l'ordre (« d'abord…, ensuite…, enfin… »).
Termine en citant brièvement la page utilisée (« d'après la page Configuration VPN »)."""

TEXT_PROMPT = """Réponds de façon concise, en Markdown si utile (étapes numérotées, `commandes`).
Termine par la ou les pages utilisées."""


class ThinkFilter:
    """Retire les blocs <think>…</think> d'un flux de texte, même coupés entre deux chunks."""
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf = ""
        self.in_think = False

    def feed(self, text: str) -> str:
        self.buf += text
        out = []
        while True:
            if self.in_think:
                i = self.buf.find(self.CLOSE)
                if i < 0:
                    # Garde la fin au cas où la balise fermante serait coupée
                    self.buf = self.buf[-(len(self.CLOSE) - 1):]
                    break
                self.buf = self.buf[i + len(self.CLOSE):]
                self.in_think = False
            else:
                i = self.buf.find(self.OPEN)
                if i >= 0:
                    out.append(self.buf[:i])
                    self.buf = self.buf[i + len(self.OPEN):]
                    self.in_think = True
                    continue
                # Ne relâche pas un éventuel début de balise "<thi"
                keep = 0
                for k in range(len(self.OPEN) - 1, 0, -1):
                    if self.buf.endswith(self.OPEN[:k]):
                        keep = k
                        break
                out.append(self.buf[:len(self.buf) - keep])
                self.buf = self.buf[len(self.buf) - keep:]
                break
        return "".join(out)

    def flush(self) -> str:
        rest, self.buf = ("" if self.in_think else self.buf), ""
        return rest


def _format_pages(pages: list) -> str:
    blocks = []
    for p in pages:
        content = p["content"]
        if len(content) > PAGE_CHARS:
            content = content[:PAGE_CHARS] + "\n[…page tronquée, utilise read_doc pour la suite]"
        kind = "Story" if p.get("kind") == "story" else "Page"
        header = f"### {kind} « {p['title']} » (fichier: {p['filename']}, tags: {', '.join(p['tags'])})"
        if p.get("symptoms"):
            header += f"\nSymptômes connus : {' ; '.join(p['symptoms'])}"
        blocks.append(f"{header}\n{content}")
    return "\n\n".join(blocks)


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}


async def run_agent(
    history: list,
    *,
    search: Callable[[str, int], list],
    read: Callable[[str], Optional[dict]],
    llm_stream: Callable[[list, Optional[list]], AsyncIterator[dict]],
    voice: bool = True,
) -> AsyncIterator[dict]:
    """Fait tourner l'assistant et émet des événements pour l'UI.

    - search(query, limit) -> [{filename, title, tags, snippet}]
    - read(filename) -> {filename, title, tags, content} | None
    - llm_stream(messages, tools) -> chunks Ollama /api/chat (stream)
    """
    history = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")]
    history = history[-HISTORY_MESSAGES:]
    question = next((m["content"] for m in reversed(history) if m["role"] == "user"), "").strip()
    if not question:
        yield {"type": "error", "error": "Question vide"}
        return

    sources = {}  # filename -> title, dans l'ordre de découverte

    # ── 1. Recherche rapide ──
    hits = search(question, FAST_RESULTS)
    yield {"type": "search", "mode": "rapide", "query": question, "results": hits}
    pages = [p for p in (read(h["filename"]) for h in hits) if p]
    for p in pages:
        sources[p["filename"]] = p["title"]

    def system_prompt(with_tools: bool) -> str:
        parts = [BASE_PROMPT]
        if with_tools:
            parts.append(TOOLS_PROMPT)
        parts.append(VOICE_PROMPT if voice else TEXT_PROMPT)
        if pages:
            parts.append("Pages trouvées par la recherche rapide :\n\n" + _format_pages(pages))
        else:
            parts.append("La recherche rapide n'a trouvé aucune page.")
        return "\n\n".join(parts)

    use_tools = True
    messages = [{"role": "system", "content": system_prompt(True)}] + history
    rounds = 0

    # ── 2. Boucle modèle / outils ──
    while True:
        tools = TOOLS if use_tools and rounds < MAX_TOOL_ROUNDS else None
        think = ThinkFilter()
        content, tool_calls, emitted = "", [], False
        try:
            async for chunk in llm_stream(messages, tools):
                msg = chunk.get("message") or {}
                tool_calls.extend(msg.get("tool_calls") or [])
                text = think.feed(msg.get("content") or "")
                if text:
                    if not emitted:
                        text = text.lstrip()
                    if text:
                        content += text
                        emitted = True
                        yield {"type": "token", "text": text}
        except ToolsUnsupported:
            if not tools:
                raise
            logger.info("🔧 Modèle sans tool calling : recherche rapide uniquement")
            use_tools = False
            messages[0] = {"role": "system", "content": system_prompt(False)}
            yield {"type": "info", "text": "Ce modèle ne sait pas utiliser d'outils : recherche rapide uniquement."}
            continue
        rest = think.flush()
        if rest:
            content += rest
            yield {"type": "token", "text": rest}

        if not tool_calls:
            break

        # ── 3. Recherche approfondie demandée par le modèle ──
        rounds += 1
        if emitted:
            yield {"type": "reset"}  # le texte précédant les appels d'outils n'est pas la réponse
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        for call in tool_calls:
            fn = call.get("function") or {}
            name, args = fn.get("name"), _parse_args(fn.get("arguments"))
            if name == "search_docs":
                query = str(args.get("query", "")).strip()
                results = search(query, 5) if query else []
                yield {"type": "search", "mode": "approfondi", "query": query, "results": results}
                result = json.dumps(results, ensure_ascii=False) if results else "Aucun résultat. Essaie d'autres mots-clés."
            elif name == "read_doc":
                page = read(str(args.get("filename", "")))
                if page:
                    sources[page["filename"]] = page["title"]
                    yield {"type": "read", "filename": page["filename"], "title": page["title"]}
                    result = _format_pages([{**page, "content": page["content"][:PAGE_CHARS * 2]}])
                else:
                    result = "Page introuvable. Utilise un nom de fichier renvoyé par search_docs."
            else:
                result = f"Outil inconnu : {name}"
            logger.info(f"🔧 Outil {name}({args}) -> {len(result)} chars")
            messages.append({"role": "tool", "content": result, "tool_name": name or ""})

    yield {"type": "done", "answer": content.strip(),
           "sources": [{"filename": f, "title": t} for f, t in sources.items()]}
