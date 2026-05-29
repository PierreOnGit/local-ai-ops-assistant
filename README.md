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
INFO - ⏳ Envoi de la requête à Ollama (timeout: 300s)...
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

## Troubleshooting

### 🔴 "Ollama indisponible" ou "Cannot connect to Ollama"

**Cause** : Ollama n'est pas lancé ou pas accessible à `http://localhost:11434`

**Solution** :

```bash
# 1. Vérifier que Ollama est lancé
ollama serve

# 2. Vérifier la connexion (depuis une autre terminal)
curl http://localhost:11434/api/tags

# 3. Vérifier la variable OLLAMA_URL dans .env
# Par défaut: OLLAMA_URL=http://localhost:11434
```

### ⏱️ "Timeout after 300 seconds"

**Cause** : Ollama prend trop de temps (le modèle est lent ou la machine est lente)

**Solution** :

```bash
# 1. Essayer avec un modèle plus rapide
OLLAMA_MODEL=qwen2.5  # Plus rapide que qwen3

# 2. Ou augmenter le timeout dans backend/main.py (ligne 71)
timeout = httpx.Timeout(10.0, read=600.0, ...)  # 600 secondes = 10 minutes

# 3. Vérifier les ressources de la machine (GPU disponible?)
```

### 📋 "Model not found" ou modèle inexistant

**Cause** : Le modèle spécifié dans `OLLAMA_MODEL` n'existe pas

**Solution** :

```bash
# 1. Voir les modèles disponibles
ollama list

# 2. Télécharger un modèle
ollama pull qwen3

# 3. Vérifier la variable OLLAMA_MODEL dans .env
```

### 🔤 "Internal Server Error" ou response manquante

**Cause** : Ollama génère une réponse invalide (JSON mal formaté, etc.)

**Solution** :

```bash
# 1. Vérifier les logs du backend
# Chercher les messages ❌ pour voir l'erreur spécifique

# 2. Essayer manuellement avec curl
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "prompt": "Test",
    "stream": false
  }'

# 3. Vérifier que Ollama répond correctement
ollama show qwen3  # Info sur le modèle
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
