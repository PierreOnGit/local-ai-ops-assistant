"""Test de bout en bout sur une vraie installation (vrai Ollama, vraie voix, vrai Whisper).

Lance l'app (uvicorn backend.main:app), puis dans un autre terminal :
    python scripts/smoke_test.py                 # http://localhost:8000
    python scripts/smoke_test.py --url http://localhost:8000 --keep

Le script crée une story de test, interroge l'Assistant, fait lire une phrase à Piper
et la fait retranscrire par Whisper. La story de test est supprimée à la fin (sauf --keep).
"""
import argparse
import json
import sys
import time

import httpx

CONVERSATION = """User: Bonjour, mon VPN FortiClient reste bloqué à 98% puis affiche l'erreur -14.
Tech: Tu es sur quelle version de FortiClient ?
User: La 6.4.
Tech: Le certificat de la passerelle a changé, les versions avant 7.2 ne l'acceptent plus.
Télécharge FortiClient 7.2 sur le portail RH, installe-le, puis reconnecte-toi à vpn.entreprise.fr
avec ton login AD.
User: C'est bon, ça passe à 100% et j'ai accès à l'intranet."""

QUESTION = "Le VPN d'une utilisatrice reste bloqué à 98%, je fais quoi ?"
SPOKEN = "Le VPN FortiClient reste bloqué à quatre-vingt-dix-huit pour cent."

results = []


def check(name, ok, detail="", warn=False):
    icon = "✅" if ok else ("⚠️ " if warn else "❌")
    results.append((name, ok or warn))
    print(f"{icon} {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--keep", action="store_true", help="garder la story de test")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.url, timeout=httpx.Timeout(10, read=900))

    # ── 1. Santé ──
    try:
        h = c.get("/health").json()
    except httpx.HTTPError as e:
        check("App joignable", False, f"{e} — l'app est-elle lancée ? (uvicorn backend.main:app)")
        return
    check("App joignable", True, args.url)
    if not check("Ollama", h["ollama"] == "ok", "ollama serve ?" if h["ollama"] != "ok" else h["model"]):
        return
    if not check("Modèle téléchargé", h["model_available"], "" if h["model_available"] else f"ollama pull {h['model']}"):
        return
    check("Voix Piper", h["tts"]["engine"] == "piper", h["tts"].get("reason") or h["tts"].get("voice", ""), warn=True)
    check("Whisper", h["stt"]["engine"] == "whisper", h["stt"].get("reason") or h["stt"].get("model", ""), warn=True)

    # ── 2. Génération d'une story ──
    t = time.time()
    r = c.post("/generate", json={"conversation": CONVERSATION, "kind": "story"})
    story = r.json() if r.status_code == 200 else {}
    if not check("Génération de story", r.status_code == 200,
                 f"{time.time() - t:.0f}s — « {story.get('title')} »" if story else r.text[:200]):
        return
    check("Symptômes extraits", len(story["symptoms"]) >= 2, " ; ".join(story["symptoms"]), warn=True)
    check("Sections de la story", all(f"## {s}" in story["content"] for s in ("Symptômes", "Résolution")),
          "Symptômes / Résolution présents", warn=True)
    filename = story["filename"]

    try:
        # ── 3. Recherche ──
        hits = c.get("/search", params={"q": QUESTION}).json()
        check("Recherche par symptôme", bool(hits) and hits[0]["filename"] == filename,
              hits[0]["title"] if hits else "aucun résultat")

        # ── 4. Assistant ──
        t = time.time()
        events, first_token = [], None
        with c.stream("POST", "/chat", json={"messages": [{"role": "user", "content": QUESTION}], "voice": True}) as r:
            for line in r.iter_lines():
                if line:
                    ev = json.loads(line)
                    events.append(ev)
                    if ev["type"] == "token" and first_token is None:
                        first_token = time.time() - t
        done = next((e for e in events if e["type"] == "done"), None)
        error = next((e for e in events if e["type"] == "error"), None)
        if check("Réponse de l'Assistant", done is not None and bool(done["answer"]),
                 error["error"] if error else f"1er mot après {first_token or 0:.1f}s, total {time.time() - t:.1f}s"):
            print("   «", done["answer"].replace("\n", " ")[:300], "»")
            deep = [e for e in events if e["type"] in ("search", "read") and e.get("mode") != "rapide"]
            tools_info = next((e["text"] for e in events if e["type"] == "info"), None)
            check("Outils (recherche approfondie)", tools_info is None,
                  tools_info or f"modèle compatible, {len(deep)} appel(s) d'outil sur cette question "
                                 "(0 est normal si la recherche rapide suffisait)", warn=True)
            check("Story citée en source", any(s["filename"] == filename for s in done["sources"]), warn=True)

        # ── 5. Voix : Piper → Whisper ──
        if h["tts"]["engine"] == "piper":
            t = time.time()
            r = c.post("/tts", json={"text": SPOKEN})
            if check("Synthèse Piper", r.status_code == 200, f"{time.time() - t:.2f}s, {len(r.content) // 1024} Ko"):
                audio = r.content
                if h["stt"]["engine"] == "whisper":
                    t = time.time()
                    r = c.post("/stt", content=audio, headers={"Content-Type": "audio/wav"})
                    text = r.json().get("text", "") if r.status_code == 200 else r.text[:200]
                    check("Transcription Whisper", r.status_code == 200 and "vpn" in text.lower(),
                          f"{time.time() - t:.1f}s (1er appel = chargement du modèle) — « {text} »")
    finally:
        if not args.keep:
            c.delete(f"/pages/{filename}")

    failed = [n for n, ok in results if not ok]
    print("\n" + ("🎉 Tout fonctionne" if not failed else f"❌ {len(failed)} échec(s) : {', '.join(failed)}"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
