# 🎯 Guide des modèles Ollama

## ⚠️ Le critère n°1 : le modèle sait-il utiliser des outils ?

L'Assistant fait d'abord une **recherche rapide**, puis laisse le modèle **creuser lui-même**
(`search_docs`, `read_doc`) si ça ne suffit pas. Cette recherche approfondie nécessite un modèle
qui gère le *tool calling* dans Ollama (badge **tools** sur [ollama.com/search](https://ollama.com/search)).

Avec un modèle sans outils, tout fonctionne quand même (génération des stories, réponses à partir
de la recherche rapide), mais l'Assistant ne peut pas chercher plus loin et l'indique dans l'interface.

| Modèle | Taille par défaut | Outils | Usage conseillé |
|--------|-------------------|:------:|-----------------|
| **qwen3** | 8B (existe en 0.6b → 32b) | ✅ | ⭐ Défaut du projet, très bon en français |
| **qwen3:4b** | 4B | ✅ | ⭐ Machine sans GPU |
| **qwen2.5** | 7B (existe en 0.5b → 72b) | ✅ | Alternative solide, pas de phase de « réflexion » |
| **qwen2.5:3b** | 3B | ✅ | CPU modeste |
| **llama3.1** | 8B | ✅ | Bon généraliste |
| **llama3.2** | 3B | ✅ | Très léger |
| **mistral** | 7B | ✅ | Bon généraliste |
| phi | 2.7B | ❌ | Tests rapides uniquement |
| neural-chat, orca-mini | 7B | ❌ | Déconseillés |
| qwen:7b (ancien Qwen 1.5) | 7B | ❌ | Remplacé par qwen2.5 / qwen3 |

> `qwen3` commence ses réponses par une phase de réflexion (`<think>…</think>`) : l'app la masque,
> mais elle rallonge le temps de réponse. Si l'Assistant te paraît lent, essaie `qwen2.5`.

---

## 💻 Quelle taille pour ta machine ?

Ordres de grandeur avec les versions quantifiées par défaut d'Ollama :

| Machine | Modèle conseillé | RAM / VRAM nécessaire |
|---------|------------------|-----------------------|
| CPU seul, 8 Go de RAM | `qwen3:4b` ou `qwen2.5:3b` | ~3-4 Go |
| CPU seul, 16 Go de RAM | `qwen3` (8B) — lent mais meilleure qualité | ~6 Go |
| GPU 6-8 Go | `qwen3` (8B) | ~6 Go |
| GPU 12 Go et + | `qwen3:14b` | ~10 Go |

Pense à garder de la place pour la voix : Whisper `small` utilise environ 1 Go de RAM en plus,
Piper quelques centaines de Mo.

Sur CPU, compte de quelques dizaines de secondes à plusieurs minutes pour générer une story,
selon la machine et la taille du modèle. Si la génération dépasse `OLLAMA_TIMEOUT` (600 s par
défaut), prends un modèle plus petit ou augmente le timeout.

---

## 🔄 Changer de modèle

```bash
# 1. Télécharger le nouveau modèle
ollama pull qwen2.5

# 2. Vérifier qu'il est là
ollama list

# 3. Mettre à jour .env
OLLAMA_MODEL=qwen2.5

# 4. Relancer l'app
uvicorn backend.main:app --reload
```

Avec Docker : `OLLAMA_MODEL=qwen2.5 docker compose up` (le modèle est téléchargé automatiquement).

---

## 🧪 Tester que le modèle gère les outils

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "qwen3",
  "stream": false,
  "messages": [{"role": "user", "content": "Cherche la procédure VPN"}],
  "tools": [{"type": "function", "function": {
    "name": "search_docs", "description": "Recherche dans la doc",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
  }}]
}'
```

- Réponse avec `"tool_calls"` → ✅ le modèle sait utiliser les outils.
- Erreur `does not support tools` → ❌ recherche rapide uniquement.

---

## 🎯 TL;DR

```
Pas de GPU      → qwen3:4b
GPU disponible  → qwen3
Trop lent ?     → qwen2.5 (pas de phase de réflexion)
```
