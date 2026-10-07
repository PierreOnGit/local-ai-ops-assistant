import os
import re
import json
import httpx
import sqlite3
import logging
from contextlib import closing
from datetime import datetime
from fastapi import FastAPI, Request
from typing import Literal
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.chat import run_agent, ToolsUnsupported
from backend.tts import tts, TTSUnavailable
from backend.stt import stt, STTUnavailable, MAX_AUDIO_BYTES

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
# Chemins absolus : l'app fonctionne quel que soit le dossier de lancement
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR  = os.path.join(BASE_DIR, "frontend")
DATA_DIR      = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
WIKI_DIR      = os.path.join(DATA_DIR, "wiki")
DB_PATH       = os.path.join(DATA_DIR, "wiki.db")

OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "qwen3")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "600"))

app = FastAPI(title="Local AI Ops Assistant")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# ── Base de données ──────────────────────────────────────────────────────────

def db():
    """Connexion SQLite fermée automatiquement (à utiliser avec `with`)."""
    return closing(sqlite3.connect(DB_PATH))

def init_db():
    os.makedirs(WIKI_DIR, exist_ok=True)
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                title     TEXT UNIQUE,
                tags      TEXT,
                filename  TEXT,
                created   TEXT
            )
        """)
        # Migration : colonnes ajoutées avec les stories
        columns = {r[1] for r in con.execute("PRAGMA table_info(pages)")}
        if "kind" not in columns:
            con.execute("ALTER TABLE pages ADD COLUMN kind TEXT DEFAULT 'page'")
        if "symptoms" not in columns:
            con.execute("ALTER TABLE pages ADD COLUMN symptoms TEXT DEFAULT '[]'")
        # Index plein texte (accents ignorés : "reseau" trouve "réseau").
        # Recréé à chaque démarrage : il est reconstruit juste après de toute façon.
        con.execute("DROP TABLE IF EXISTS pages_fts")
        con.execute("""
            CREATE VIRTUAL TABLE pages_fts USING fts5(
                filename UNINDEXED, title, symptoms, tags, content,
                tokenize = 'unicode61 remove_diacritics 2'
            )
        """)
        con.commit()
    reindex_all()

def load_tags(raw) -> list:
    """Décode la colonne `tags` (JSON) sans jamais lever d'exception."""
    if not raw:
        return []
    try:
        tags = json.loads(raw)
        return [str(t) for t in tags] if isinstance(tags, list) else []
    except (ValueError, TypeError):
        return []

def normalize_tags(tags) -> list:
    """Tags en minuscules, sans espaces superflus ni doublons, triés."""
    cleaned = set()
    for t in tags:
        t = re.sub(r"\s+", "-", str(t).strip().strip("#*`\"'").strip().lower())
        if t:
            cleaned.add(t)
    return sorted(cleaned)

def get_existing_tags():
    try:
        with db() as con:
            rows = con.execute("SELECT tags FROM pages").fetchall()
        return normalize_tags(t for r in rows for t in load_tags(r[0]))
    except sqlite3.Error as e:
        logger.error(f"Error fetching existing tags: {e}")
        return []

def safe_wiki_path(filename: str):
    """Chemin d'une page dans WIKI_DIR, ou None si le nom est suspect (path traversal)."""
    if not filename or filename != os.path.basename(filename) or not filename.endswith(".md"):
        return None
    path = os.path.realpath(os.path.join(WIKI_DIR, filename))
    if os.path.dirname(path) != os.path.realpath(WIKI_DIR):
        return None
    return path

# ── Recherche ────────────────────────────────────────────────────────────────

def read_page(filename: str):
    """Page complète (métadonnées + contenu) ou None."""
    path = safe_wiki_path(filename)
    if not path or not os.path.exists(path):
        return None
    with db() as con:
        row = con.execute(
            "SELECT title, tags, kind, symptoms FROM pages WHERE filename = ?", (filename,)
        ).fetchone()
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if not row:
        row = (filename[:-3], None, "page", None)
    return {
        "filename": filename, "title": row[0], "tags": load_tags(row[1]),
        "kind": row[2] or "page", "symptoms": load_tags(row[3]), "content": content,
    }

def index_page(filename: str):
    """(Ré)indexe une page dans la recherche plein texte."""
    page = read_page(filename)
    with db() as con:
        con.execute("DELETE FROM pages_fts WHERE filename = ?", (filename,))
        if page:
            con.execute(
                "INSERT INTO pages_fts (filename, title, symptoms, tags, content) VALUES (?,?,?,?,?)",
                (filename, page["title"], "\n".join(page["symptoms"]), " ".join(page["tags"]), page["content"]),
            )
        con.commit()

def reindex_all():
    """Reconstruit l'index depuis la base (rapide, fait au démarrage)."""
    with db() as con:
        con.execute("DELETE FROM pages_fts")
        con.commit()
        filenames = [r[0] for r in con.execute("SELECT filename FROM pages").fetchall()]
    for filename in filenames:
        index_page(filename)
    logger.info(f"🔎 Index de recherche : {len(filenames)} page(s)")

STOPWORDS = set("""
le la les l un une des de du d et ou en a à au aux pour par sur sous dans avec sans
comment quoi quel quelle quels quelles qui que qu est sont être ai as avoir faire fait
je j tu il elle on nous vous ils elles me m te t se s ce c cette ces mon ma mes ton ta tes son sa ses
ne n pas plus y lui leur leurs dont où ça cela peut peux dois doit faut il-y bonjour salut merci stp svp
the a an of to is how what
""".split())

def fts_query(text: str) -> str:
    """Transforme une question libre en requête FTS5 (mots-clés OR, préfixes)."""
    words = [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1 and w not in STOPWORDS]
    seen = []
    for w in words:
        if w not in seen:
            seen.append(w)
    return " OR ".join(f'"{w}"*' for w in seen[:12])

def search_pages(query: str, limit: int = 5) -> list:
    q = fts_query(query)
    if not q:
        return []
    with db() as con:
        try:
            rows = con.execute(
                """
                SELECT f.filename, f.title, f.tags,
                       snippet(pages_fts, 4, '«', '»', '…', 16),
                       bm25(pages_fts, 0.0, 8.0, 10.0, 4.0, 1.0) AS score,
                       p.kind, p.symptoms
                FROM pages_fts f LEFT JOIN pages p ON p.filename = f.filename
                WHERE pages_fts MATCH ?
                ORDER BY score LIMIT ?
                """,
                (q, limit),
            ).fetchall()
        except sqlite3.OperationalError as e:
            logger.warning(f"⚠️ Requête de recherche invalide ({q!r}): {e}")
            return []
    return [
        {"filename": r[0], "title": r[1], "tags": r[2].split() if r[2] else [], "snippet": r[3],
         "kind": r[5] or "page", "symptoms": load_tags(r[6])}
        for r in rows
    ]

init_db()

# ── LLM ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un expert IT. Génère une page wiki Markdown structurée.

Format EXACT (ne mets rien avant) :
TITLE: Titre court
TAGS: tag1, tag2, tag3
---
# Titre

## Résumé
1-2 phrases clés.

## Procédure
- Point 1
- Point 2
(Supprime si N/A)

## Détails techniques
Infos importantes.
"""

STORY_PROMPT = """Tu es un expert IT. À partir de la conversation, rédige une STORY d'incident :
la fiche qu'un technicien retrouvera quand il rencontrera le même problème.

Format EXACT (ne mets rien avant) :
TITLE: Titre court qui décrit le problème (ex: VPN FortiClient bloqué à 98%)
TAGS: tag1, tag2, tag3
SYMPTOMS: symptôme 1 ; symptôme 2 ; message d'erreur exact
---
# Titre

## Symptômes
- Ce que l'utilisateur ou le technicien constate (messages d'erreur exacts, comportement)

## Contexte
Environnement concerné : poste, logiciel, version, site… (Supprime si N/A)

## Diagnostic
- Vérifications à faire pour confirmer la cause, dans l'ordre
- Cause identifiée

## Résolution
1. Étape 1 (commandes exactes entre `backticks`)
2. Étape 2

## Vérification
Comment confirmer que le problème est réglé.

SYMPTOMS : 3 à 6 formulations courtes, telles qu'un technicien les dirait au téléphone
(ex: "le vpn reste bloqué à 98%", "erreur -14"), séparées par des points-virgules.
N'invente rien qui ne soit pas dans la conversation : si une section n'a pas d'information, supprime-la.
"""

PROMPTS = {"story": STORY_PROMPT, "page": SYSTEM_PROMPT}

class OllamaError(Exception):
    """Erreur côté Ollama (indisponible, timeout, modèle absent…)."""

async def ask_ollama(conversation: str, existing_tags: list = None, kind: str = "story") -> str:
    logger.info(f"🚀 Appel Ollama - Modèle: {OLLAMA_MODEL}, URL: {OLLAMA_URL}, type: {kind}")
    logger.debug(f"📝 Prompt utilisateur (premiers 200 chars): {conversation[:200]}")

    system_prompt = PROMPTS[kind]
    if existing_tags:
        tags_str = ", ".join(existing_tags)
        system_prompt += f"\n\nIMPORTANT: Voici la liste des tags existants : {tags_str}.\n" \
                         f"Tu DOIS réutiliser ces tags exacts si le contenu de la conversation correspond à l'un d'eux.\n" \
                         f"Ne crée un nouveau tag que si AUCUN des tags existants n'est pertinent.\n" \
                         f"Les tags doivent être au format minuscule, simples et sans espaces (ex: 'docker', 'vpn', 'ssl')."
        logger.info(f"🏷️ Tags existants fournis au prompt: {tags_str}")
    else:
        system_prompt += f"\n\nIMPORTANT: Génère des tags pertinents en minuscules pour catégoriser cette page. Préfère des tags courts, précis et standards (ex: nginx, docker, ssl, vpn, debian)."

    # La génération peut être très longue sur CPU : timeout de lecture configurable
    timeout = httpx.Timeout(10.0, read=OLLAMA_TIMEOUT, write=30.0, pool=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            logger.info(f"⏳ Envoi de la requête à Ollama (timeout: {OLLAMA_TIMEOUT:.0f}s)...")
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"Conversation :\n\n{conversation}\n\n"
                              + ("Génère la story." if kind == "story" else "Génère la page wiki."),
                    "system": system_prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
            )
            r.raise_for_status()
            logger.info(f"✅ Réponse Ollama reçue (status: {r.status_code})")
        except httpx.ConnectError as e:
            logger.error(f"❌ Impossible de se connecter à Ollama ({OLLAMA_URL}): {e}")
            logger.error(f"   💡 Conseil: Ollama est-il lancé? (ollama serve)")
            raise OllamaError(f"Cannot connect to Ollama at {OLLAMA_URL}. Is it running? (ollama serve)")
        except httpx.TimeoutException as e:
            logger.error(f"❌ Timeout Ollama: {e!r}")
            raise OllamaError(
                f"Ollama timeout after {OLLAMA_TIMEOUT:.0f} seconds. "
                f"Try a lighter model (see MODELS.md) or increase OLLAMA_TIMEOUT."
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ollama retourne une erreur HTTP {e.response.status_code}: {e.response.text[:500]}")
            if e.response.status_code == 404:
                raise OllamaError(f"Model '{OLLAMA_MODEL}' not found. Run: ollama pull {OLLAMA_MODEL}")
            raise OllamaError(f"Ollama error {e.response.status_code}: {e.response.text[:200]}")

    try:
        response_text = r.json()["response"]
    except (ValueError, KeyError, TypeError) as e:
        logger.error(f"❌ Réponse Ollama invalide: {e!r}")
        raise OllamaError("Invalid response from Ollama (missing 'response' field)")

    logger.info(f"📄 Réponse générée ({len(response_text)} caractères)")
    logger.debug(f"📋 Contenu (premiers 500 chars):\n{response_text[:500]}")
    return response_text

async def ollama_chat_stream(messages: list, tools: list = None):
    """Appel streamé à /api/chat. Lève ToolsUnsupported si le modèle ne gère pas les outils."""
    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": True, "options": {"temperature": 0.2}}
    if tools:
        payload["tools"] = tools
    timeout = httpx.Timeout(10.0, read=OLLAMA_TIMEOUT, write=30.0, pool=30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as r:
                if r.status_code >= 400:
                    body = (await r.aread()).decode(errors="replace")
                    if tools and "does not support tools" in body:
                        raise ToolsUnsupported()
                    if r.status_code == 404:
                        raise OllamaError(f"Model '{OLLAMA_MODEL}' not found. Run: ollama pull {OLLAMA_MODEL}")
                    raise OllamaError(f"Ollama error {r.status_code}: {body[:200]}")
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise OllamaError(f"Ollama error: {chunk['error']}")
                    yield chunk
    except httpx.ConnectError:
        raise OllamaError(f"Cannot connect to Ollama at {OLLAMA_URL}. Is it running? (ollama serve)")
    except httpx.TimeoutException:
        raise OllamaError(f"Ollama timeout after {OLLAMA_TIMEOUT:.0f} seconds.")

# Lignes d'en-tête tolérantes : "TITLE: x", "**Title:** x", "## TAGS : a, b"…
_HEADER_RE = re.compile(
    r"^[\s>#*_`]*(TITLE|TITRE|TAGS|SYMPT[OÔ]MS?|SYMPT[OÔ]MES)[\s*_`]*:[\s*_`]*(.*?)[\s*_`]*$", re.IGNORECASE
)
_SYMPTOMS_SECTION_RE = re.compile(r"^##\s*Sympt[oô]mes?\s*$(.*?)(?=^##\s|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)

def clean_symptoms(items) -> list:
    out = []
    for item in items:
        item = re.sub(r"\s+", " ", str(item)).strip(" -*•\"'`.").strip()
        if item and item.lower() not in (o.lower() for o in out):
            out.append(item[:150])
    return out[:10]
_THINK_RE  = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

def parse_response(raw: str) -> dict:
    logger.info("🔍 Parsing de la réponse Ollama...")
    # Les modèles "raisonnants" (qwen3, deepseek-r1…) préfixent leur réponse par <think>…</think>
    text = _THINK_RE.sub("", raw).strip()
    # Certains modèles entourent toute la réponse d'un bloc ```markdown … ```
    fenced = re.fullmatch(r"```[\w-]*\n(.*)\n```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    title, tags, symptoms = None, [], []
    body_lines = []
    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            key, value = m.group(1).upper(), m.group(2).strip()
            if key in ("TITLE", "TITRE") and title is None and value:
                title = value
                continue
            if key == "TAGS" and not tags:
                tags = [t for t in re.split(r"[,;]", value) if t.strip()]
                continue
            if key.startswith("SYMPT") and not symptoms:
                symptoms = re.split(r"[;|]", value)
                continue
        body_lines.append(line)

    # Retire le séparateur '---' qui suit l'en-tête (et seulement celui-là)
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    if body_lines and body_lines[0].strip() == "---":
        body_lines.pop(0)
    content = "\n".join(body_lines).strip()

    # Fallback titre : premier heading Markdown
    if not title:
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    title = (title or "Sans titre").strip("*_` ")[:120] or "Sans titre"

    if not content:
        content = f"# {title}\n"
    tags = normalize_tags(tags)

    # Fallback symptômes : puces de la section "## Symptômes"
    symptoms = clean_symptoms(symptoms)
    if not symptoms:
        m = _SYMPTOMS_SECTION_RE.search(content)
        if m:
            symptoms = clean_symptoms(
                l.strip()[1:] for l in m.group(1).splitlines() if l.strip()[:1] in ("-", "*", "•")
            )

    logger.info(f"✅ Parse complète - Titre: '{title}', Tags: {len(tags)}, Symptômes: {len(symptoms)}, "
                f"Contenu: {len(content)} chars")
    return {"title": title, "tags": tags, "symptoms": symptoms, "content": content}

def make_filename(title: str) -> str:
    """Nom de fichier unique pour un titre. Un même titre réutilise son fichier."""
    with db() as con:
        row = con.execute("SELECT filename FROM pages WHERE title = ?", (title,)).fetchone()
        if row and row[0]:
            return row[0]
        taken = {r[0] for r in con.execute("SELECT filename FROM pages").fetchall()}

    slug = re.sub(r"[^\w]+", "_", title.lower()).strip("_")[:50] or "page"
    filename, n = f"{slug}.md", 2
    while filename in taken or os.path.exists(os.path.join(WIKI_DIR, filename)):
        filename = f"{slug}_{n}.md"
        n += 1
    return filename

# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()

class GenerateRequest(BaseModel):
    conversation: str
    kind: Literal["story", "page"] = "story"

@app.post("/generate")
async def generate(body: GenerateRequest):
    conversation = body.conversation.strip()
    if not conversation:
        return JSONResponse({"error": "Conversation vide"}, status_code=400)

    logger.info(f"📥 Nouvelle requête de génération ({len(conversation)} caractères)")
    try:
        raw = await ask_ollama(conversation, get_existing_tags(), kind=body.kind)
    except OllamaError as e:
        logger.error(f"❌ Erreur Ollama: {e}")
        return JSONResponse({"error": str(e)}, status_code=503)

    try:
        parsed   = parse_response(raw)
        filename = make_filename(parsed["title"])

        # Fichier Markdown
        with open(os.path.join(WIKI_DIR, filename), "w", encoding="utf-8") as f:
            f.write(parsed["content"])
        logger.info(f"✅ Fichier sauvegardé: {WIKI_DIR}/{filename}")

        # Base de données
        with db() as con:
            con.execute(
                "INSERT OR REPLACE INTO pages (title, tags, filename, created, kind, symptoms) "
                "VALUES (?,?,?,?,?,?)",
                (parsed["title"], json.dumps(parsed["tags"]), filename, datetime.now().isoformat(),
                 body.kind, json.dumps(parsed["symptoms"], ensure_ascii=False)),
            )
            con.commit()
        index_page(filename)

        logger.info(f"🎉 Génération réussie - Titre: '{parsed['title']}'")
        return {**parsed, "kind": body.kind, "filename": filename}
    except Exception as e:
        logger.exception(f"❌ Erreur lors de l'enregistrement: {e}")
        return JSONResponse({"error": f"Erreur interne: {e}"}, status_code=500)

class UpdateTagsRequest(BaseModel):
    tags: list[str]

@app.put("/pages/{filename}/tags")
async def update_page_tags(filename: str, body: UpdateTagsRequest):
    logger.info(f"📥 Mise à jour des tags pour {filename} : {body.tags}")
    normalized_tags = normalize_tags(body.tags)
    with db() as con:
        cur = con.execute(
            "UPDATE pages SET tags = ? WHERE filename = ?",
            (json.dumps(normalized_tags), filename),
        )
        con.commit()
    if cur.rowcount == 0:
        logger.warning(f"⚠️ Page introuvable pour mise à jour des tags : {filename}")
        return JSONResponse({"error": "Page introuvable"}, status_code=404)

    index_page(filename)
    logger.info(f"✅ Tags mis à jour pour {filename} : {normalized_tags}")
    return {"filename": filename, "tags": normalized_tags}

@app.get("/tags")
async def list_tags():
    with db() as con:
        rows = con.execute("SELECT tags FROM pages").fetchall()
    tag_counts = {}
    for r in rows:
        for t in normalize_tags(load_tags(r[0])):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(tag_counts.items())]

@app.get("/pages")
async def list_pages():
    with db() as con:
        rows = con.execute(
            "SELECT id, title, tags, filename, created, kind, symptoms FROM pages ORDER BY created DESC"
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "tags": load_tags(r[2]), "filename": r[3], "created": r[4] or "",
         "kind": r[5] or "page", "symptoms": load_tags(r[6])}
        for r in rows
    ]

@app.get("/pages/{filename}")
async def get_page(filename: str):
    filepath = safe_wiki_path(filename)
    if not filepath or not os.path.exists(filepath):
        return JSONResponse({"error": "introuvable"}, status_code=404)
    with open(filepath, encoding="utf-8") as f:
        return {"content": f.read()}

@app.delete("/pages/{filename}")
async def delete_page(filename: str):
    filepath = safe_wiki_path(filename)
    if not filepath:
        return JSONResponse({"error": "introuvable"}, status_code=404)
    with db() as con:
        cur = con.execute("DELETE FROM pages WHERE filename = ?", (filename,))
        con.commit()
    file_existed = os.path.exists(filepath)
    if file_existed:
        os.remove(filepath)
    index_page(filename)
    if cur.rowcount == 0 and not file_existed:
        return JSONResponse({"error": "introuvable"}, status_code=404)
    logger.info(f"🗑️ Page supprimée: {filename}")
    return {"deleted": filename}

@app.get("/search")
async def search(q: str = "", limit: int = 5):
    return search_pages(q, max(1, min(limit, 20)))

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    voice: bool = True

@app.post("/chat")
async def chat(body: ChatRequest):
    """Assistant "call" : flux NDJSON d'événements (search, read, token, reset, done, error)."""
    history = [m.model_dump() for m in body.messages]
    logger.info(f"📞 Question : {history[-1]['content'][:200] if history else ''}")

    async def events():
        try:
            async for event in run_agent(
                history, search=search_pages, read=read_page,
                llm_stream=ollama_chat_stream, voice=body.voice,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except OllamaError as e:
            logger.error(f"❌ Erreur Ollama: {e}")
            yield json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False) + "\n"
        except Exception as e:
            logger.exception(f"❌ Erreur assistant: {e}")
            yield json.dumps({"type": "error", "error": f"Erreur interne: {e}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")

class TTSRequest(BaseModel):
    text: str

@app.post("/tts")
async def text_to_speech(body: TTSRequest):
    """Synthèse vocale locale (Piper) -> audio/wav. 503 si Piper n'est pas disponible."""
    if not body.text.strip():
        return JSONResponse({"error": "Texte vide"}, status_code=400)
    try:
        audio = await run_in_threadpool(tts.synthesize, body.text)
    except TTSUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    return Response(audio, media_type="audio/wav")

def stt_vocabulary(max_chars: int = 400) -> str:
    """Vocabulaire de la base (tags, titres) pour guider l'orthographe de Whisper."""
    with db() as con:
        rows = con.execute("SELECT title, tags FROM pages ORDER BY created DESC").fetchall()
    words = []
    for title, tags in rows:
        for w in load_tags(tags) + [title]:
            if w not in words:
                words.append(w)
    vocab = ", ".join(words)[:max_chars]
    return f"Support informatique. Vocabulaire : {vocab}." if vocab else "Support informatique."

@app.post("/stt")
async def speech_to_text(request: Request):
    """Transcription locale (Whisper). Corps de la requête = l'audio brut (webm, ogg, wav…)."""
    audio = await request.body()
    if not audio:
        return JSONResponse({"error": "Audio vide"}, status_code=400)
    if len(audio) > MAX_AUDIO_BYTES:
        return JSONResponse({"error": "Enregistrement trop long"}, status_code=413)
    try:
        return await run_in_threadpool(stt.transcribe, audio, stt_vocabulary())
    except STTUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.get("/health")
async def health():
    ollama_ok, model_ok = False, False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
        ollama_ok = r.status_code == 200
        if ollama_ok:
            names = {m.get("name", "") for m in r.json().get("models", [])}
            # "qwen3" correspond à "qwen3:latest"
            model_ok = OLLAMA_MODEL in names or f"{OLLAMA_MODEL}:latest" in names
    except Exception:
        pass
    return {
        "app": "ok",
        "ollama": "ok" if ollama_ok else "ko",
        "model": OLLAMA_MODEL,
        "model_available": model_ok,
        "tts": await run_in_threadpool(tts.status),
        "stt": stt.status(),
    }
