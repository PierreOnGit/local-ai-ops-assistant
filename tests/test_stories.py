import sqlite3
import importlib

from backend.main import parse_response

STORY = """TITLE: VPN FortiClient bloqué à 98%
TAGS: vpn, forticlient
SYMPTOMS: le vpn reste bloqué à 98% ; erreur -14 ; "credential or ssl vpn configuration is wrong"
---
# VPN FortiClient bloqué à 98%

## Symptômes
- Connexion bloquée à 98%

## Résolution
1. Mettre à jour FortiClient
"""


def test_parse_story_symptoms_header():
    p = parse_response(STORY)
    assert p["symptoms"] == ["le vpn reste bloqué à 98%", "erreur -14", "credential or ssl vpn configuration is wrong"]
    assert "SYMPTOMS" not in p["content"]


def test_parse_symptoms_from_section_when_header_missing():
    raw = "TITLE: Outlook lent\nTAGS: outlook\n---\n# Outlook lent\n\n## Symptômes\n- Outlook met 2 min à s'ouvrir\n- * Recherche vide\n\n## Résolution\n- Réindexer"
    assert parse_response(raw)["symptoms"] == ["Outlook met 2 min à s'ouvrir", "Recherche vide"]


def test_generate_story_and_search_by_symptom(client, fake_ollama):
    fake_ollama.response = STORY
    d = client.post("/generate", json={"conversation": "x"}).json()
    assert d["kind"] == "story" and len(d["symptoms"]) == 3
    assert fake_ollama.calls[-1][2] == "story"

    fake_ollama.response = "TITLE: Guide VPN\nTAGS: vpn\n---\n# Guide VPN\nInstallation du vpn, du vpn, du vpn."
    client.post("/generate", json={"conversation": "y", "kind": "page"})
    assert fake_ollama.calls[-1][2] == "page"

    res = client.get("/search", params={"q": "mon vpn bloque à 98 %"}).json()
    assert res[0]["title"] == "VPN FortiClient bloqué à 98%"
    assert res[0]["kind"] == "story" and "erreur -14" in res[0]["symptoms"]
    pages = {p["title"]: p for p in client.get("/pages").json()}
    assert pages["Guide VPN"]["kind"] == "page" and pages["Guide VPN"]["symptoms"] == []


def test_invalid_kind_rejected(client, fake_ollama):
    assert client.post("/generate", json={"conversation": "x", "kind": "roman"}).status_code == 422


def test_old_database_is_migrated(tmp_path, monkeypatch):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "old.md").write_text("# Vieille page\nimprimante")
    con = sqlite3.connect(tmp_path / "wiki.db")
    con.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT UNIQUE, tags TEXT, filename TEXT, created TEXT)")
    con.execute("INSERT INTO pages (title, tags, filename, created) VALUES ('Vieille page', '[\"print\"]', 'old.md', '2025-01-01')")
    con.execute("CREATE VIRTUAL TABLE pages_fts USING fts5(filename UNINDEXED, title, tags, content)")
    con.commit()
    con.close()

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.main as main
    main = importlib.reload(main)
    assert main.search_pages("imprimante")[0]["kind"] == "page"


def test_story_symptoms_given_to_agent(client, fake_ollama, app_module, monkeypatch):
    fake_ollama.response = STORY
    client.post("/generate", json={"conversation": "x"})
    seen = {}

    async def llm(messages, tools=None):
        seen["system"] = messages[0]["content"]
        yield {"message": {"content": "Mets à jour FortiClient."}}

    monkeypatch.setattr(app_module, "ollama_chat_stream", llm)
    client.post("/chat", json={"messages": [{"role": "user", "content": "vpn bloqué 98%"}]})
    assert "Story « VPN FortiClient bloqué à 98% »" in seen["system"]
    assert "Symptômes connus : le vpn reste bloqué à 98% ; erreur -14" in seen["system"]


# ── TTS ──

def test_tts_unavailable_returns_503(client, app_module, tmp_path, monkeypatch):
    from backend.tts import PiperTTS
    monkeypatch.setattr(app_module, "tts", PiperTTS(voice="absente", voices_dir=str(tmp_path)))
    r = client.post("/tts", json={"text": "Bonjour"})
    assert r.status_code == 503 and "introuvable" in r.json()["error"]
    assert client.get("/health").json()["tts"]["engine"] == "navigateur"


def test_tts_with_fake_voice(client, app_module, monkeypatch):
    from backend.tts import PiperTTS
    monkeypatch.setattr(app_module, "tts", PiperTTS())
    class FakeVoice:
        def synthesize_wav(self, text, wav):
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
            wav.writeframes(b"\0\0" * 100)

    monkeypatch.setattr(app_module.tts, "_voice", FakeVoice())
    r = client.post("/tts", json={"text": "Bonjour"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF"
    assert client.get("/health").json()["tts"]["engine"] == "piper"
    assert client.post("/tts", json={"text": "  "}).status_code == 400
