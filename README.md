# 🤖 Local AI Ops Assistant

> Transforme des conversations IT en pages wiki Markdown — 100% local, zéro cloud.

**[🚀 Démarrage rapide](#démarrage-rapide) • [📖 Stack](#stack) • [🆘 Troubleshooting](#troubleshooting) • [🗺️ Roadmap](#roadmap)**

---

## 🚀 Démarrage rapide

### Prérequis
- Python 3.8+
- [Ollama](https://ollama.com) + un modèle (ex: `ollama pull qwen3`)

### Installation (2 min)

```bash
git clone https://github.com/ton-username/local-ai-ops-assistant
cd local-ai-ops-assistant
pip install -r requirements.txt
```

### Lancer l'app

**Option 1 : Sans Docker (recommandé pour le dev)**
```bash
uvicorn backend.main:app --reload
```

**Option 2 : Avec Docker**
```bash
docker compose up
```

Puis ouvre **[http://localhost:8000](http://localhost:8000)** 🎉

---

## ⚙️ Configuration

Crée un `.env` à la racine (ou copie `.env.example`) :

```bash
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3
```

**Modèles recommandés** :
- `qwen3` — Bon rapport qualité/vitesse
- `qwen2.5` — Plus rapide
- `deepseek-coder-v2` — Spécialisé IT

---

## 📖 Stack

| Composant | Tech |
|-----------|------|
| 🔧 Backend | Python + FastAPI |
| 🧠 LLM | Ollama (local, hors ligne) |
| 💾 Stockage | SQLite + fichiers Markdown |
| 🎨 Frontend | HTML/CSS/JS (fichier unique) |

---

## 🔍 Debugging

Les logs affichent chaque étape :

```
🚀 Appel Ollama - Modèle: qwen3
⏳ Envoi de la requête (timeout: 300s)...
✅ Réponse reçue (2543 caractères)
🎉 Génération réussie - Titre: "Configuration VPN"
```

Pour plus de détails :

```bash
# Dans backend/main.py, ligne 19 :
logging.basicConfig(level=logging.DEBUG)  # Au lieu de INFO
```

---

## 🆘 Troubleshooting

### ❌ "Ollama indisponible" / "Cannot connect"
```bash
# ✅ Solution : Lancer Ollama
ollama serve

# Vérifier la connexion
curl http://localhost:11434/api/tags
```

### ⏱️ "Timeout after 300 seconds"
```bash
# ✅ Solution 1 : Utiliser un modèle plus rapide
OLLAMA_MODEL=qwen2.5

# ✅ Solution 2 : Augmenter le timeout (backend/main.py, ligne 71)
timeout = httpx.Timeout(10.0, read=600.0, ...)  # 600s = 10 min
```

### 📋 "Model not found"
```bash
# ✅ Solution : Télécharger le modèle
ollama list          # Voir les modèles
ollama pull qwen3    # Télécharger
```

### 🔤 "Internal Server Error"
```bash
# ✅ Solution : Tester Ollama directement
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "prompt": "Test",
    "stream": false
  }'
```

---

## 📁 Structure

```
.
├── backend/main.py      ← Backend FastAPI (~220 lignes)
├── frontend/index.html  ← Frontend complet (~700 lignes)
├── data/
│   └── wiki/            ← Pages générées (.md)
├── docker-compose.yml
├── requirements.txt
└── README.md (ce fichier)
```

---

## 🗺️ Roadmap

| Phase | Fonctionnalité | Statut |
|-------|---|---|
| **1** | Wiki auto (texte → Markdown) | ✅ MVP |
| **2** | RAG (questions/réponses sur wiki) | 📅 Août |
| **3** | Ingestion (PDF, DOCX, logs) | 📅 Sept |
| **4** | Diagnostic de logs IA | 📅 Oct |
| **5** | Agents multi-rôles | 📅 Nov |
| **6** | Interface voix (Whisper + Piper) | 📅 Déc |

---

## 📜 Licence

MIT
