# DocuMind AI

Plateforme SaaS de GED intelligente, multi-tenant et AI-native.

> **État : v0.4 — Phases 1-3 : GED, vues, référentiels et Intelligence IA (classification, extraction, Prompt Studio, crédits).**
> Voir [`PROJECT_STATUS.md`](PROJECT_STATUS.md) pour le détail et la suite.

## Ce qui fonctionne aujourd'hui

- **Multi-tenant natif** : isolation applicative *et* PostgreSQL Row Level Security (FORCE RLS), tenant résolu depuis le jeton signé, jamais depuis le client.
- **Authentification** : Argon2id, JWT court (15 min) + refresh token opaque en cookie httpOnly, rotation et détection de rejeu, rate limiting Redis.
- **RBAC granulaire** : 56 permissions `ressource:action` sur 16 ressources, 6 rôles système, rôles personnalisés, protection anti-escalade de privilèges.
- **GED** : dossiers arborescents, upload multi-fichiers, contrôle par signature binaire (anti-spoofing, rejet des macros), SHA-256, détection de doublons, versioning, check-in/check-out, corbeille / restauration / purge, copie, relations, tags.
- **Pipeline documentaire asynchrone** (Celery) : antivirus ClamAV, extraction couche texte PDF, **OCR Tesseract réel** (pages scannées et images), détection de langue, indexation plein texte, publication. Étapes idempotentes, rejouables, tracées.
- **Types documentaires & Metadata Designer** : 11 types de champs, règles de validation, champs sensibles, schémas versionnés.
- **Validation humaine** : champs obligatoires / financiers à confirmer avant publication.
- **Recherche** plein texte (titre, nom de fichier, contenu OCR) avec pertinence, filtres, tri, pagination.
- **Vues de documents** : l'administrateur configure et partage des filtres (dont une vue par défaut pour toute l'organisation) ; chaque utilisateur enregistre ses propres vues et choisit sa vue par défaut.
- **Référentiels (objets métier)** : éléments non documentaires configurables (fournisseurs, clients, projets…) liés aux documents, utilisés comme propriétés de référence et pour **alimenter automatiquement les métadonnées** (ex. choisir le fournisseur d'une facture remplit nom et TVA).
- **Audit infalsifiable** : journal append-only (trigger PostgreSQL) chaîné par hachage, vérification d'intégrité, export CSV.
- **Pilot (Super Admin)** : provisioning de tenants en une action, plans, quotas, suspension / réactivation.
- **Interface** React professionnelle, thème clair/sombre, entièrement connectée à l'API.

- **Intelligence IA** : fournisseurs multi-provider (Claude, OpenAI, Azure, Gemini, modèles locaux), classification et extraction automatiques avec garde-fous, Prompt Studio versionné, registre de consommation et quotas — voir [`docs/AI_CONFIGURATION.md`](docs/AI_CONFIGURATION.md).

Le découpage documentaire, la recherche sémantique / Lina (RAG), les workflows et les connecteurs sont planifiés (phases 3b à 9). Tant qu'ils ne sont pas livrés, l'interface et le pipeline affichent explicitement « non configuré » — rien n'est simulé.

## Base de données Supabase

Voir [`supabase/README.md`](supabase/README.md) : schéma dédié `smartged`, rôle applicatif sans contournement RLS, migrations SQL prêtes.

## Démarrage rapide (Docker)

```bash
cp .env.example .env            # définir DOCUMIND_SECRET_KEY (openssl rand -hex 32) et le Super Admin
docker compose up --build       # → http://localhost:8080
docker compose --profile antivirus up   # avec ClamAV
```

Créer un premier client :

```bash
docker compose exec api python -m app.cli create-tenant \
  --name "Atlas Industries" --slug atlas \
  --admin-email admin@atlas.com --admin-password 'Choisir-Un-Mdp-2026'
```

ou depuis l'interface *Pilot* en se connectant avec le Super Admin défini dans `.env`.

## Développement local

Prérequis : Python 3.12+, Node 22+, PostgreSQL 16, Redis 7, `tesseract-ocr` (+ `fra`), `poppler-utils`.

```bash
# Backend
cd backend
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload                       # API → http://localhost:8000/api/v1/docs
celery -A app.workers.celery_app.celery_app worker -Q documents_priority,documents,dead_letter

# Frontend
cd frontend
npm install
npm run dev                                          # → http://localhost:5173 (proxy /api → :8000)
```

## Tests

```bash
cd backend && pytest -q          # 45 tests : auth, RBAC, isolation inter-tenant (API + RLS), OCR réel, GED, vues, référentiels, IA
cd frontend && npm test          # Vitest
```

## Arborescence

```
backend/   FastAPI · SQLAlchemy 2 · Alembic · Celery
  app/api/v1/routers   endpoints REST (OpenAPI : /api/v1/docs)
  app/services         règles métier
  app/models           modèle de données
  app/security         auth, contexte tenant, permissions, antivirus
  app/ocr              moteur OCR interchangeable
  app/storage          stockage objet (local dev / S3 / Azure Blob)
  app/workers          pipeline documentaire Celery
  migrations/          schéma + politiques RLS
frontend/  React 19 · TypeScript · Vite · TanStack Query · Zustand · Tailwind · Radix
docs/      architecture, sécurité, déploiement, ADR
```
