# 🤖 Local AI Ops Assistant

> Transforme des conversations IT en pages wiki Markdown, puis réponds aux techniciens
> (à l'écrit ou à la voix) en fouillant cette base — 100% local, zéro cloud.

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
# Voix française pour les réponses vocales (~60 Mo, une seule fois)
python -m piper.download_voices fr_FR-siwis-medium --download-dir voices
```

### Lancer l'app

**Option 1 : Sans Docker (recommandé pour le dev)**
```bash
uvicorn backend.main:app --reload
```

**Option 2 : Avec Docker** (Ollama + téléchargement du modèle inclus)
```bash
docker compose up
# Autre modèle : OLLAMA_MODEL=phi docker compose up
```
> Le premier lancement télécharge le modèle (plusieurs Go), patience.

Puis ouvre **[http://localhost:8000](http://localhost:8000)** 🎉

---

## 🩺 Stories d'incidents

À l'ingestion, choisis **Story d'incident** (par défaut) ou **Page wiki**.
Une story transforme un échange de support en fiche réutilisable :

```
TITLE / TAGS / SYMPTOMS (formulations "au téléphone" : « le vpn reste bloqué à 98% » ; « erreur -14 »)
## Symptômes → ## Contexte → ## Diagnostic → ## Résolution → ## Vérification
```

Les **symptômes** sont indexés avec le plus fort poids dans la recherche : quand un tech décrit
ce qu'il voit, c'est la story au symptôme le plus proche qui remonte. L'assistant vérifie que les
symptômes correspondent, guide la résolution dans l'ordre puis donne la vérification.

---

## 📞 Assistant (mode "call")

Onglet **Assistant** : le technicien pose sa question (au clavier ou au 🎤), l'IA fouille la
Knowledge Base et répond à voix haute.

```
Question ──► ⚡ Recherche rapide (index plein texte SQLite FTS5, quelques ms)
                │   les meilleures pages sont données au modèle
                ▼
             Le modèle répond… ou creuse si ça ne suffit pas :
             🔎 search_docs (autres mots-clés)  📖 read_doc (page complète)   ← max 4 tours
                ▼
             Réponse streamée, lue phrase par phrase 🔊 + sources cliquables
```

- **Recherche approfondie** : nécessite un modèle qui gère les *tools*
  (`qwen3`, `qwen2.5`, `llama3.1`, `mistral`…). Avec un modèle sans tools (`phi`…),
  l'assistant se contente de la recherche rapide (et le signale).
- **Voix** : les réponses sont lues par **[Piper](https://github.com/OHF-Voice/piper1-gpl)**
  (synthèse neuronale locale, ~0,2 s par phrase sur CPU). Si Piper ou la voix n'est pas installé,
  l'app se rabat sur la voix du navigateur — l'onglet Assistant indique le moteur utilisé.
  Changer de voix : `PIPER_VOICE` dans `.env`.
- **Dictée 🎤** : utilise la reconnaissance vocale du navigateur. Sur Chrome elle passe par
  les serveurs de Google (pas 100% local). Une transcription locale (Whisper) est prévue.
- API : `POST /chat` (flux NDJSON d'événements `search`, `read`, `token`, `done`…),
  `GET /search?q=...` pour la recherche seule, `POST /tts` (texte → WAV).

---

## ⚙️ Configuration

Crée un `.env` à la racine (ou copie `.env.example`) :

```bash
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3
OLLAMA_TIMEOUT=600   # secondes max par génération
LOG_LEVEL=INFO       # DEBUG pour voir prompts et réponses brutes
```

Le badge en bas à gauche de l'interface indique l'état : `● qwen3` (vert) si tout va bien,
`● Ollama KO` si Ollama n'est pas lancé, `● qwen3 absent` si le modèle n'est pas téléchargé.

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

Pour plus de détails, lance avec `LOG_LEVEL=DEBUG` (dans `.env` ou en variable d'environnement).

---

## 🧪 Tests

Les tests utilisent un faux Ollama : pas besoin d'avoir un modèle pour les lancer.

```bash
pip install -r requirements-dev.txt
pytest
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

### ⏱️ "Ollama timeout after 600 seconds"
```bash
# ✅ Solution 1 : Utiliser un modèle plus rapide
OLLAMA_MODEL=qwen2.5

# ✅ Solution 2 : Augmenter le timeout (dans .env)
OLLAMA_TIMEOUT=1200  # 20 min
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
├── backend/main.py      ← Backend FastAPI (wiki, recherche, API)
├── backend/chat.py      ← Assistant : recherche rapide → outils → réponse
├── backend/tts.py       ← Synthèse vocale Piper
├── voices/              ← Voix Piper téléchargées (non versionné)
├── frontend/index.html  ← Frontend complet (fichier unique)
├── frontend/vendor/     ← marked + DOMPurify embarqués (fonctionne hors ligne)
├── tests/               ← Tests pytest (faux Ollama)
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
| **1** | Wiki auto (texte → Markdown), tags, suppression | ✅ MVP |
| **2** | Assistant "call" : recherche rapide + approfondie, réponse vocale | 🚧 En cours |
| **2b** | Stories d'incidents (symptômes), voix locale Piper | ✅ |
| **2c** | Dictée locale (Whisper) | 📅 |
| **3** | Ingestion (PDF, DOCX, logs) | 📅 Sept |
| **4** | Diagnostic de logs IA | 📅 Oct |
| **5** | Agents multi-rôles | 📅 Nov |
| **6** | Interface voix (Whisper + Piper) | 📅 Déc |

---

## 📜 Licence

MIT
