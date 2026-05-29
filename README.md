# 🤖 Local AI Ops Assistant

> Transforme des conversations IT en pages wiki Markdown — 100% local, zéro cloud.

---

## Démarrage rapide

### Sans Docker (recommandé pour le dev)

```bash
# 1. Cloner le repo
git clone https://github.com/ton-username/local-ai-ops-assistant
cd local-ai-ops-assistant

# 2. Installer Ollama + un modèle
# https://ollama.com
# ollama pull qwen3

# 3. Installer les dépendances Python
pip install -r requirements.txt

# 4. Créer un .env (optionnel)
# OLLAMA_URL=http://localhost:11434
# OLLAMA_MODEL=qwen3

# 5. Lancer le serveur
uvicorn backend.main:app --reload
```

Ouvre [http://localhost:8000](http://localhost:8000) → colle une conversation → clique **Generate Wiki**.

### Avec Docker

```bash
docker compose up
```

---

## Debugging / Verbose

Le backend affiche des logs détaillés de ce qu'Ollama génère :

```
INFO - 🚀 Appel Ollama - Modèle: qwen3, URL: http://localhost:11434
INFO - 📝 Prompt utilisateur (premiers 200 chars): ...
INFO - ✅ Réponse Ollama reçue (status: 200)
INFO - 📄 Réponse générée (X caractères)
INFO - 🔍 Parsing de la réponse Ollama...
INFO - ✅ Parse complète - Titre: '...', Tags: 3, Contenu: Y chars
INFO - 💾 Création du fichier: mon_titre.md
INFO - ✅ Fichier sauvegardé: ./data/wiki/mon_titre.md
INFO - 🎉 Génération réussie
```

Pour voir les logs en temps réel :

```bash
# Niveau INFO (par défaut)
uvicorn backend.main:app --reload

# Niveau DEBUG (plus verbose, voir contenu complet)
# Modifier logging.basicConfig(level=logging.DEBUG) dans main.py
```

---

## Ce que ça fait (MVP)

1. Tu colles une conversation (Teams, mail, notes...)
2. Tu cliques **Generate Wiki**
3. Le LLM local analyse et structure
4. Une page Markdown est créée dans `data/wiki/`
5. Elle s'affiche dans le navigateur + s'ajoute à la sidebar

---

## Stack

| | |
|---|---|
| Backend | Python + FastAPI |
| LLM | Ollama (Qwen3 / DeepSeek) |
| Stockage | SQLite + fichiers `.md` |
| Frontend | HTML/CSS/JS (un seul fichier) |

---

## Structure

```
local-ai-ops-assistant/
├── backend/
│   └── main.py          ← tout le backend (150 lignes)
├── frontend/
│   └── index.html       ← tout le frontend
├── data/
│   ├── conversations/   ← sauvegarde optionnelle
│   └── wiki/            ← pages .md générées
├── docker-compose.yml
├── .env
└── requirements.txt
```

---

## Roadmap

- **Phase 1 (juin–juillet)** — Wiki automatique ✅
- **Phase 2 (août)** — RAG : questions/réponses sur le wiki
- **Phase 3 (septembre)** — Ingestion PDF / DOCX
- **Phase 4 (octobre)** — Diagnostic de logs
- **Phase 5 (novembre)** — Agents multi-rôles
- **Phase 6 (décembre)** — Interface voix (Whisper + Piper)

---

## Licence

MIT
