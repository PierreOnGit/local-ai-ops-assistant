# 📋 Guide de publication sur GitHub

## Étape 1: Préparer le repository local

```bash
cd c:\Users\pierre.dupont\Downloads\local-ai-ops-assistant-mvp

# Initialiser git (s'il n'existe pas)
git init

# Configurer git (optionnel, si tu ne l'as pas fait)
git config user.name "Ton Nom"
git config user.email "ton.email@example.com"

# Vérifier le statut
git status
```

## Étape 2: Créer un repository sur GitHub

1. Va sur https://github.com/new
2. Crée un nouveau repository :
   - **Name**: `local-ai-ops-assistant`
   - **Description**: `Transforme des conversations IT en pages wiki Markdown — 100% local, zéro cloud`
   - **Public** (pour que tout le monde voie)
   - **Ajoute une LICENSE** → choose MIT
   - **Ajoute un .gitignore** → Python (on a déjà un bon)
3. **Crée le repo** sans initialiser README (on en a un)

## Étape 3: Connecter ton repo local au remote

```bash
# Ajouter le remote (remplace USERNAME par ton username GitHub)
git remote add origin https://github.com/USERNAME/local-ai-ops-assistant.git

# Ou si tu utilises SSH :
# git remote add origin git@github.com:USERNAME/local-ai-ops-assistant.git

# Vérifier
git remote -v
```

## Étape 4: Commit et Push

```bash
# Stage tous les fichiers
git add .

# Commit
git commit -m "Initial commit: Local AI Ops Assistant MVP

- Backend FastAPI avec appel Ollama
- Frontend HTML/CSS/JS (fichier unique)
- Ingestion texte et génération wiki Markdown
- Logging verbose pour debugging
- Support Docker
- Base SQLite pour stockage des pages"

# Push vers GitHub (main branch)
git branch -M main
git push -u origin main
```

## Étape 5: Ajouter des issues et milestones (optionnel)

Sur GitHub, tu peux ajouter :
- Des **issues** pour tracker les bugs et features
- Des **milestones** pour organiser les phases

Exemple d'issue pour le phase 2 (RAG) :

```
Title: Phase 2 - RAG: questions/réponses sur le wiki
Description: 
- Indexer les pages du wiki
- Implémentation du retrieval sémantique
- Intégration dans le frontend
Labels: enhancement, phase-2
Milestone: Phase 2 (Août)
```

## Commandes utiles après

```bash
# Voir l'historique
git log --oneline

# Créer une branche pour une feature
git checkout -b feature/phase-2-rag

# Faire des commits
git add backend/
git commit -m "Add RAG retrieval system"

# Pusher la branche
git push origin feature/phase-2-rag

# Créer une Pull Request sur GitHub (dans l'interface web)
```

## Liens utiles

- README.md — déjà prêt avec instructions de démarrage
- .gitignore — ignore les données et venv
- .env.example — exemple de configuration
- requirements.txt — dépendances Python

Bon courage ! 🚀
