# 🤖 Local AI Ops Assistant

> Transforme des conversations IT en pages wiki Markdown, puis réponds aux techniciens
> (à l'écrit ou à la voix) en fouillant cette base — 100% local, zéro cloud.

**[🚀 Démarrage rapide](#-démarrage-rapide) • [📞 Assistant](#-assistant-mode-call) • [⚙️ Configuration](#️-configuration) • [🆘 Troubleshooting](#-troubleshooting) • [🗺️ Roadmap](#️-roadmap)**

---

## 🚀 Démarrage rapide

### Prérequis
- Python 3.10+ (3.11 recommandé, c'est la version de l'image Docker)
- [Ollama](https://ollama.com) + un modèle qui sait utiliser des outils (ex: `ollama pull qwen3`,
  voir [MODELS.md](MODELS.md))
- ~1 Go de disque pour la voix (Piper) et la dictée (Whisper)

### Installation (2 min)

```bash
git clone https://github.com/ton-username/local-ai-ops-assistant
cd local-ai-ops-assistant
pip install -r requirements.txt
# Voix française pour les réponses vocales (~60 Mo, une seule fois)
python -m piper.download_voices fr_FR-siwis-medium --download-dir voices
# Modèle Whisper pour la dictée (~480 Mo pour "small", sinon téléchargé au 1er usage)
python -m backend.stt download
```

### Lancer l'app

**Option 1 : Sans Docker (recommandé pour le dev)**
```bash
uvicorn backend.main:app --reload
```

**Option 2 : Avec Docker** (Ollama + téléchargement du modèle inclus)
```bash
docker compose up
# Autre modèle : OLLAMA_MODEL=qwen2.5 docker compose up
```
> Le build télécharge la voix Piper et le modèle Whisper ; le premier lancement télécharge
> le modèle Ollama (plusieurs Go). Patience.

Puis ouvre **[http://localhost:8000](http://localhost:8000)** 🎉

### Premier essai (5 min)
1. **Ingestion** → *Story d'incident* → colle un échange de support → **Générer**.
2. **Assistant** → pose une question qui décrit le symptôme (« le VPN reste bloqué à 98% »).
3. Clique sur 🎤 pour poser la suivante à la voix, coche **🔁 Mains libres** pour enchaîner.

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
- **Dictée 🎤** : transcription locale par **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)**.
  Clique sur 🎤, parle : l'enregistrement s'arrête tout seul après 1,5 s de silence.
  Whisper reçoit le vocabulaire de ta base (tags, titres) pour bien écrire "FortiClient", "spooler"…
  Modèle réglable avec `WHISPER_MODEL` (`base` = plus rapide, `medium` = plus précis).
  Sans faster-whisper, l'app utilise la dictée du navigateur (qui, sur Chrome, passe par Google).
- **🔁 Mains libres** : après chaque réponse vocale, le micro se relance tout seul — on enchaîne
  les questions comme dans un appel. Cliquer sur 🎤 pendant que l'IA parle lui coupe la parole.
- ⚠️ Le micro ne fonctionne que sur `http://localhost` ou en **https** (règle des navigateurs) :
  pour l'utiliser depuis un autre poste, il faut passer l'app derrière un reverse proxy https.
- API : `POST /chat` (flux NDJSON d'événements `search`, `read`, `token`, `done`…),
  `GET /search?q=...` pour la recherche seule, `POST /tts` (texte → WAV),
  `POST /stt` (audio brut → texte).

---

## ⚙️ Configuration

Crée un `.env` à la racine (ou copie `.env.example`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Adresse d'Ollama |
| `OLLAMA_MODEL` | `qwen3` | Modèle utilisé (voir [MODELS.md](MODELS.md)) |
| `OLLAMA_TIMEOUT` | `600` | Secondes max laissées au modèle |
| `LOG_LEVEL` | `INFO` | `DEBUG` pour voir prompts et réponses brutes |
| `DATA_DIR` | `./data` | Base SQLite + pages Markdown |
| `PIPER_VOICE` | `fr_FR-siwis-medium` | Voix Piper (nom dans `./voices` ou chemin `.onnx`) |
| `WHISPER_MODEL` | `small` | `tiny` / `base` (rapide) … `medium` / `large-v3` (précis) |
| `WHISPER_DEVICE` | `auto` | `cpu` ou `cuda` |
| `WHISPER_COMPUTE` | `int8` | `float16` sur GPU |

L'interface affiche l'état des moteurs :
- badge en bas à gauche : `● qwen3` (vert) si tout va bien, `● Ollama KO` si Ollama n'est pas
  lancé, `● qwen3 absent` si le modèle n'est pas téléchargé ;
- onglet Assistant : `(Piper)` ou `(voix du navigateur)` à côté de *Réponse vocale*,
  et l'info-bulle du 🎤 indique si la dictée passe par Whisper ou par le navigateur.

---

## 📖 Stack

| Composant | Tech |
|-----------|------|
| 🔧 Backend | Python + FastAPI |
| 🧠 LLM | Ollama (local, hors ligne), tool calling pour la recherche approfondie |
| 🔎 Recherche | SQLite FTS5 (plein texte, accents ignorés) |
| 💾 Stockage | SQLite + fichiers Markdown |
| 🔊 Voix | Piper (synthèse) + faster-whisper (transcription), tout en local |
| 🎨 Frontend | HTML/CSS/JS (fichier unique, sans CDN) |

---

## 🔍 Debugging

Les logs affichent chaque étape :

```
🚀 Appel Ollama - Modèle: qwen3
⏳ Envoi de la requête (timeout: 600s)...
✅ Réponse reçue (2543 caractères)
🎉 Génération réussie - Titre: "Configuration VPN"
```

Pour plus de détails, lance avec `LOG_LEVEL=DEBUG` (dans `.env` ou en variable d'environnement).

---

## 🧪 Tests

Les tests utilisent un faux Ollama et un faux Whisper : pas besoin de modèle pour les lancer.

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

### 🔎 L'assistant ne fait jamais de "Recherche approfondie"
Le modèle ne sait pas utiliser d'outils (`phi`, `neural-chat`, `orca-mini`…) : l'Assistant affiche
alors « Ce modèle ne sait pas utiliser d'outils ». Passe à `qwen3`, `qwen2.5`, `llama3.1` ou
`mistral` (voir [MODELS.md](MODELS.md)).

### 🔇 Réponses lues par la "voix du navigateur" au lieu de Piper
Survole `(voix du navigateur)` dans l'onglet Assistant pour voir la raison. Le plus souvent la voix
n'est pas téléchargée :
```bash
python -m piper.download_voices fr_FR-siwis-medium --download-dir voices
```

### 🎤 Micro inaccessible / bouton 🎤 absent
- Le micro ne marche que sur `http://localhost` ou en **https** : depuis un autre poste,
  passe par un reverse proxy https (Caddy, nginx…).
- Bouton absent : ni faster-whisper ni la dictée du navigateur ne sont disponibles
  (`pip install -r requirements.txt`, ou utilise Chrome / Edge).

### 🐢 Première dictée très lente
Au premier usage, Whisper charge (et télécharge si besoin) le modèle. Fais-le à l'avance avec
`python -m backend.stt download`. Si chaque transcription reste lente : `WHISPER_MODEL=base`.

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
├── backend/stt.py       ← Transcription Whisper
├── models/whisper/      ← Modèles Whisper téléchargés (non versionné)
├── voices/              ← Voix Piper téléchargées (non versionné)
├── frontend/index.html  ← Frontend complet (fichier unique)
├── frontend/vendor/     ← marked + DOMPurify embarqués (fonctionne hors ligne)
├── tests/               ← Tests pytest (faux Ollama)
├── data/
│   └── wiki/            ← Pages générées (.md)
├── docker-compose.yml   ← App + Ollama + téléchargement du modèle
├── .env.example         ← Toutes les variables de configuration
├── MODELS.md            ← Quel modèle Ollama choisir
├── requirements.txt     ← (requirements-dev.txt pour les tests)
└── README.md (ce fichier)
```

---

## 🗺️ Roadmap

| Phase | Fonctionnalité | Statut |
|-------|---|---|
| **1** | Wiki auto (texte → Markdown), tags, suppression | ✅ |
| **2** | Assistant "call" : recherche rapide + approfondie, réponse streamée | ✅ |
| **2b** | Stories d'incidents (symptômes) | ✅ |
| **2c** | Voix 100% locale : Piper (réponses) + Whisper (dictée), mode mains libres | ✅ |
| **3** | Ingestion PDF, DOCX, logs (boutons « Bientôt » déjà dans l'interface) | 📅 |
| **4** | Diagnostic de logs par l'IA | 📅 |
| **5** | Agents multi-rôles | 📅 |

### 🧪 À valider en conditions réelles
Développé et testé avec un faux Ollama et un faux Whisper (le vrai décodage audio, la voix Piper
et le navigateur sont, eux, testés). Reste à vérifier sur une vraie machine :
- [ ] `qwen3` utilise bien `search_docs` / `read_doc` quand la recherche rapide ne suffit pas,
      et seulement dans ce cas
- [ ] Qualité et vitesse de Whisper `small` sur la machine cible
- [ ] Téléchargement de la voix Piper et du modèle Whisper depuis HuggingFace, build Docker

### 🔧 Améliorations prévues
- [ ] **Appel → story automatique** : à la fin d'un appel, l'IA rédige la story à partir de
      l'échange (la base se remplit toute seule)
- [ ] **« Ça a résolu ? »** après chaque réponse, pour faire remonter les stories qui marchent
- [ ] **Questions de suite** : la recherche rapide ne regarde que la dernière question
      (« et pour celle du 2e étage ? » perd le contexte)
- [ ] **Recherche sémantique** (embeddings via Ollama) en complément du plein texte, pour
      trouver « connexion distante » quand la story dit « VPN »
- [ ] **Éditer le contenu** d'une story / page (aujourd'hui : tags uniquement)
- [ ] **Authentification** : aujourd'hui toute personne sur le réseau peut lire et supprimer
- [ ] **HTTPS** prêt à l'emploi (reverse proxy dans le `docker-compose`) pour le micro sur
      d'autres postes

---

## 📜 Licence

MIT
