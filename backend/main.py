import os
import re
import json
import httpx
import sqlite3
import logging
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend"), name="static")

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3")
WIKI_DIR     = "./data/wiki"
DB_PATH      = "./data/wiki.db"

# ── Base de données ──────────────────────────────────────────────────────────

def init_db():
    os.makedirs(WIKI_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
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
    con.close()

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

async def ask_ollama(conversation: str) -> str:
    logger.info(f"🚀 Appel Ollama - Modèle: {OLLAMA_MODEL}, URL: {OLLAMA_URL}")
    logger.debug(f"📝 Prompt utilisateur (premiers 200 chars): {conversation[:200]}")
    
    # Timeout plus long pour la génération (peut être très long)
    # 300 secondes = 5 minutes
    timeout = httpx.Timeout(10.0, read=300.0, write=30.0, pool=30.0)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            logger.info(f"⏳ Envoi de la requête à Ollama (timeout: 300s)...")
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"Conversation :\n\n{conversation}\n\nGénère la page wiki.",
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                },
            )
            r.raise_for_status()
            logger.info(f"✅ Réponse Ollama reçue (status: {r.status_code})")
            
            try:
                response_data = r.json()
                if "response" not in response_data:
                    logger.error("❌ Champ 'response' manquant dans la réponse")
                    raise ValueError("Ollama response missing 'response' field")
                
                response_text = response_data["response"]
                logger.info(f"📄 Réponse générée ({len(response_text)} caractères)")
                logger.debug(f"📋 Contenu (premiers 500 chars):\n{response_text[:500]}")
                
                return response_text
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"❌ Erreur JSON: {str(e)}")
                raise ValueError(f"Invalid response from Ollama: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"❌ Impossible de se connecter à Ollama ({OLLAMA_URL})")
            logger.error(f"   Erreur: {str(e)}")
            logger.error(f"   💡 Conseil: Ollama est-il lancé? (ollama serve)")
            raise ValueError(f"Cannot connect to Ollama at {OLLAMA_URL}. Is it running?")
        except httpx.ReadTimeout as e:
            logger.error(f"❌ Timeout lors de la lecture de la réponse Ollama")
            logger.error(f"   Erreur: {str(e)}")
            logger.error(f"   💡 Conseil: Ollama prend trop de temps (>300s), ou ne répond pas")
            raise ValueError(f"Ollama timeout after 300 seconds. The model may be too slow or not responding.")
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ollama retourne une erreur HTTP {e.response.status_code}")
            logger.error(f"   Réponse: {e.response.text[:500]}")
            raise ValueError(f"Ollama error {e.response.status_code}: {e.response.text[:200]}")

def parse_response(raw: str) -> dict:
    logger.info("🔍 Parsing de la réponse Ollama...")
    title   = "Sans titre"
    tags    = []
    content = raw

    for line in raw.splitlines():
        if line.startswith("TITLE:"):
            title = line[6:].strip()
            logger.debug(f"   📌 Titre trouvé: {title}")
        elif line.startswith("TAGS:"):
            tags = [t.strip() for t in line[5:].split(",") if t.strip()]
            logger.debug(f"   🏷️  Tags trouvés: {tags}")

    if "---" in raw:
        content = raw.split("---", 1)[1].strip()
        logger.debug(f"   📋 Séparateur '---' trouvé, contenu: {len(content)} chars")
    else:
        logger.warn("   ⚠️  Séparateur '---' non trouvé dans la réponse")

    logger.info(f"✅ Parse complète - Titre: '{title}', Tags: {len(tags)}, Contenu: {len(content)} chars")
    return {"title": title, "tags": tags, "content": content}

# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("frontend/index.html", encoding="utf-8") as f:
        return f.read()

class GenerateRequest(BaseModel):
    conversation: str

@app.post("/generate")
async def generate(body: GenerateRequest):
    logger.info(f"📥 Nouvelle requête de génération ({len(body.conversation)} caractères)")
    try:
        raw    = await ask_ollama(body.conversation)
        parsed = parse_response(raw)

        # Fichier Markdown
        slug     = re.sub(r"[^\w]", "_", parsed["title"].lower())[:50]
        filename = f"{slug}.md"
        logger.info(f"💾 Création du fichier: {filename}")
        
        with open(os.path.join(WIKI_DIR, filename), "w", encoding="utf-8") as f:
            f.write(parsed["content"])
        logger.info(f"✅ Fichier sauvegardé: {WIKI_DIR}/{filename}")

        # Base de données
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT OR REPLACE INTO pages (title, tags, filename, created) VALUES (?,?,?,?)",
            (parsed["title"], json.dumps(parsed["tags"]), filename, datetime.now().isoformat()),
        )
        con.commit()
        con.close()
        logger.info(f"✅ Page enregistrée en base: {parsed['title']}")

        logger.info(f"🎉 Génération réussie - Titre: '{parsed['title']}'")
        return {"title": parsed["title"], "tags": parsed["tags"], "content": parsed["content"]}
    
    except ValueError as e:
        # Erreurs spécifiques d'Ollama (timeout, connexion, etc.)
        error_msg = str(e)
        logger.error(f"❌ Erreur Ollama: {error_msg}")
        return JSONResponse({"error": error_msg}, status_code=503)
    except httpx.HTTPStatusError as e:
        error_msg = f"Ollama error: {e.response.status_code} - {e.response.text[:500]}"
        logger.error(f"❌ {error_msg}")
        return JSONResponse({"error": error_msg}, status_code=503)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"❌ Erreur: {str(e)}\n{error_trace}")
        return JSONResponse(
            {"error": str(e), "details": error_trace},
            status_code=500
        )

@app.get("/pages")
async def list_pages():
    con  = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT id, title, tags, filename, created FROM pages ORDER BY created DESC"
    ).fetchall()
    con.close()
    return [
        {"id": r[0], "title": r[1], "tags": json.loads(r[2]), "filename": r[3], "created": r[4]}
        for r in rows
    ]

@app.get("/pages/{filename:path}")
async def get_page(filename: str):
    filepath = os.path.join(WIKI_DIR, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "introuvable"}, status_code=404)
    with open(filepath, encoding="utf-8") as f:
        return {"content": f.read()}

@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        ollama_ok = False
    return {"app": "ok", "ollama": "ok" if ollama_ok else "ko", "model": OLLAMA_MODEL}
