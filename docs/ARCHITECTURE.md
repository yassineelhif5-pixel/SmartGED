# Architecture — DocuMind AI

## Vue d'ensemble

```
 Navigateur (React SPA)
        │  HTTPS — JWT en mémoire, refresh token en cookie httpOnly/SameSite=strict
        ▼
 nginx (statique + reverse proxy /api, CSP)
        │
        ▼
 FastAPI (monolithe modulaire)  ──────►  PostgreSQL 16 (RLS, tsvector, pgvector)
   api/ → services/ → models/   ──────►  Stockage objet (S3 / Azure Blob / local dev)
        │ enqueue                  ┌──►  ClamAV (INSTREAM)
        ▼                          │
 Redis (broker, rate limit) ──► Celery workers ── pipeline documentaire ──► Tesseract / OCR cloud
```

## Couches backend

| Couche | Rôle |
|---|---|
| `api/v1/routers` | HTTP uniquement : validation Pydantic, dépendances de sécurité, audit, sérialisation |
| `security/context.py` | Résout l'utilisateur, la session, **vérifie l'appartenance au tenant**, charge les permissions, lie la session SQL au tenant |
| `services/` | Règles métier, transactions, quotas |
| `repositories/` | Accès tenant-aware (`get_owned` : un objet d'un autre tenant = 404) |
| `models/` | SQLAlchemy 2 typé ; `TenantScoped` marque les tables soumises à RLS |
| `workers/` | Celery + pipeline à étapes persistées |
| `ocr/`, `storage/`, `ai/` | Abstractions de fournisseurs interchangeables |

## Isolation multi-tenant

1. Le tenant actif est inscrit dans le JWT signé (`tid`) et **revérifié à chaque requête** contre une appartenance active et un tenant actif.
2. Chaque transaction exécute `set_config('app.tenant_id', …, true)` via un listener `after_begin` (persiste après les commits intermédiaires).
3. Politique RLS identique sur toutes les tables métier : `tenant_id = app.tenant_id` (USING et WITH CHECK), `FORCE ROW LEVEL SECURITY` pour que le propriétaire des tables y soit soumis.
4. Les opérations plateforme (provisioning, login) ouvrent explicitement une session `bypass_rls` — jamais à partir d'une donnée client.
5. Tests : lecture, écriture, recherche, relations, doublons, en-tête `X-Tenant-ID` forgé, requête SQL sans filtre.

## Pipeline documentaire

`antivirus → text_extraction → language → classification → metadata_extraction → indexing → publication`

- Une ligne `processing_jobs` unique par (document, version, étape) ⇒ idempotence et reprise.
- Chaque étape s'exécute dans sa propre transaction ⇒ progression visible en temps réel (polling TanStack Query).
- Statuts : `completed`, `failed`, `skipped`, `not_configured` (capacité absente, jamais simulée).
- Échec technique ⇒ retry Celery exponentiel (3) puis file `dead_letter`.
- Fichier infecté ⇒ document `rejected`, téléchargement bloqué (quarantaine).

## Modèle de données (phases 1-2)

SaaS : `tenants`, `subscription_plans`, `tenant_settings`, `tenant_modules`, `tenant_quotas`, `system_settings`
Identité : `users`, `user_tenants`, `roles`, `permissions`, `role_permissions`, `user_roles`, `groups`, `group_members`, `user_sessions`
GED : `folders`, `documents`, `document_versions`, `document_types`, `metadata_definitions`, `document_metadata_values`, `document_tags`, `document_relations`, `ocr_pages`, `processing_jobs`
Transverse : `audit_logs`, `notifications`

Les binaires ne sont jamais stockés en base : clé objet `tenants/{tenant}/documents/{doc}/v{n}/{sha256}.{ext}`.
