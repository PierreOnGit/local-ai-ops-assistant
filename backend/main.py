import os
import re
import json
import httpx
import sqlite3
import logging
from contextlib import closing
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

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
        con.commit()

init_db()

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

class OllamaError(Exception):
    """Erreur côté Ollama (indisponible, timeout, modèle absent…)."""

async def ask_ollama(conversation: str, existing_tags: list = None) -> str:
    logger.info(f"🚀 Appel Ollama - Modèle: {OLLAMA_MODEL}, URL: {OLLAMA_URL}")
    logger.debug(f"📝 Prompt utilisateur (premiers 200 chars): {conversation[:200]}")

    system_prompt = SYSTEM_PROMPT
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
                    "prompt": f"Conversation :\n\n{conversation}\n\nGénère la page wiki.",
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

# Lignes d'en-tête tolérantes : "TITLE: x", "**Title:** x", "## TAGS : a, b"…
_HEADER_RE = re.compile(r"^[\s>#*_`]*(TITLE|TITRE|TAGS)[\s*_`]*:[\s*_`]*(.*?)[\s*_`]*$", re.IGNORECASE)
_THINK_RE  = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

def parse_response(raw: str) -> dict:
    logger.info("🔍 Parsing de la réponse Ollama...")
    # Les modèles "raisonnants" (qwen3, deepseek-r1…) préfixent leur réponse par <think>…</think>
    text = _THINK_RE.sub("", raw).strip()
    # Certains modèles entourent toute la réponse d'un bloc ```markdown … ```
    fenced = re.fullmatch(r"```[\w-]*\n(.*)\n```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    title, tags = None, []
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

    logger.info(f"✅ Parse complète - Titre: '{title}', Tags: {len(tags)}, Contenu: {len(content)} chars")
    return {"title": title, "tags": tags, "content": content}

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

@app.post("/generate")
async def generate(body: GenerateRequest):
    conversation = body.conversation.strip()
    if not conversation:
        return JSONResponse({"error": "Conversation vide"}, status_code=400)

    logger.info(f"📥 Nouvelle requête de génération ({len(conversation)} caractères)")
    try:
        raw = await ask_ollama(conversation, get_existing_tags())
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
                "INSERT OR REPLACE INTO pages (title, tags, filename, created) VALUES (?,?,?,?)",
                (parsed["title"], json.dumps(parsed["tags"]), filename, datetime.now().isoformat()),
            )
            con.commit()

        logger.info(f"🎉 Génération réussie - Titre: '{parsed['title']}'")
        return {**parsed, "filename": filename}
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
            "SELECT id, title, tags, filename, created FROM pages ORDER BY created DESC"
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "tags": load_tags(r[2]), "filename": r[3], "created": r[4] or ""}
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
    if cur.rowcount == 0 and not file_existed:
        return JSONResponse({"error": "introuvable"}, status_code=404)
    logger.info(f"🗑️ Page supprimée: {filename}")
    return {"deleted": filename}

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
    }
