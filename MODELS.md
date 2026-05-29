# 🎯 Guide des modèles Ollama

Quelle machine as-tu ? Choisis le modèle approprié :

## 💻 CPU seulement (pas de GPU)

| Modèle | Taille | Temps/req | Qualité | Recommandé |
|--------|--------|-----------|---------|-----------|
| **phi** | 2.7B | 20-30s | 🟨 Moyen | ⭐⭐⭐ |
| **neural-chat** | 7B | 60-120s | 🟩 Bon | ⭐⭐ |
| **orca-mini** | 7B | 60-120s | 🟩 Bon | ⭐ |
| mistral | 7B | 60-120s | 🟩 Bon | ⭐ |
| qwen:7b | 7B | 120-180s | 🟩 Bon | ⭐ |

**Commande :**
```bash
ollama pull phi
# Dans .env :
OLLAMA_MODEL=phi
```

---

## 🖥️ GPU (NVIDIA/AMD/Metal)

| Modèle | Taille | Temps/req | Qualité | Recommandé |
|--------|--------|-----------|---------|-----------|
| phi | 2.7B | 5-10s | 🟨 Moyen | ⭐ |
| neural-chat | 7B | 10-20s | 🟩 Bon | ⭐⭐ |
| **qwen:7b** | 7B | 15-25s | 🟩 Bon | ⭐⭐⭐ |
| mistral | 7B | 15-25s | 🟩 Bon | ⭐⭐⭐ |
| qwen2.5 | 8B | 15-25s | 🟩 Bon | ⭐⭐ |
| qwen3 | 14B | 20-40s | 🟩🟩 Très bon | ⭐⭐ |

**Commande :**
```bash
ollama pull qwen:7b
# Dans .env :
OLLAMA_MODEL=qwen:7b
```

---

## 🚀 Performances réelles

### CPU (Intel i7-10700K)
- `phi` : 20-30s ✅
- `neural-chat` : 90-120s 
- `qwen:7b` : 150-200s 
- `qwen3` : 300-400s ❌

### GPU (NVIDIA RTX 3070)
- `phi` : 5-10s ✅
- `qwen:7b` : 15-20s ✅✅
- `qwen3` : 20-35s ✅✅
- `qwen:32b` : 60-80s

---

## 🧪 Test rapide

```bash
# 1. Télécharger
ollama pull phi

# 2. Tester
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "phi",
    "prompt": "Configure VPN FortiClient",
    "stream": false
  }'

# 3. Voir le temps dans la console Ollama
```

---

## 💡 Recommandations

### Tu as peu de VRAM (< 4GB) ou CPU seul ?
→ **phi** (2.7B) — le plus rapide

### Tu as une bonne machine CPU (i7+) ?
→ **neural-chat** ou **orca-mini** (7B) — bon compromis

### Tu as un GPU ?
→ **qwen:7b** (7B) — meilleur rapport qualité/vitesse

### Tu veux la meilleure qualité (pas grave si lent) ?
→ **qwen3** (14B) + GPU

---

## 🔄 Changer de modèle

```bash
# 1. Télécharger le nouveau modèle
ollama pull phi

# 2. Vérifier qu'il est là
ollama list

# 3. Mettre à jour .env
OLLAMA_MODEL=phi

# 4. Relancer l'app
uvicorn backend.main:app --reload
```

---

## 📊 Comparatif détaillé

**phi** (2.7B)
- ✅ Très rapide (20-30s)
- ✅ Léger
- ⚠️ Qualité moyenne
- 👍 Parfait pour tester / CPU faible

**neural-chat** (7B)
- ✅ Rapide (60-120s)
- ✅ Bonne qualité
- ✅ Bon sur CPU
- 👍 Meilleur compromis CPU

**qwen:7b** (7B)
- ✅ Rapide avec GPU (15-25s)
- ✅ Bonne qualité
- ⚠️ Lent sur CPU (150-200s)
- 👍 Best all-around avec GPU

**qwen3** (14B)
- ✅ Très bonne qualité
- ❌ Très lent sur CPU (300s+)
- ✅ Rapide avec GPU puissant
- 👍 Pour GPU uniquement

---

## 🎯 TL;DR

```
CPU uniquement    → phi
GPU disponible    → qwen:7b
Pas sûr ?         → neural-chat
```
