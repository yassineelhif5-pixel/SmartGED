# SmartGED sur Supabase

La base SmartGED vit dans un schéma PostgreSQL dédié **`smartged`** :

- il n'est **pas exposé** par l'API de données Supabase (PostgREST) — seul le backend FastAPI y accède ;
- il peut cohabiter sans conflit avec d'autres tables dans le même projet ;
- l'isolation multi-tenant repose sur la Row Level Security (`FORCE RLS`) de chaque table.

## 1. Créer la structure

Deux migrations, à appliquer dans l'ordre (SQL editor Supabase, `supabase db push` ou MCP) :

| Fichier | Contenu |
|---|---|
| `migrations/20261122000100_smartged_schema.sql` | 39 tables, enums, index, politiques RLS, trigger d'audit append-only, `alembic_version` = `0004` |
| `migrations/20261122000200_smartged_app_role.sql` | rôle `smartged_app` (NOBYPASSRLS), droits, révocation `anon` / `authenticated` |

Ces fichiers sont générés depuis Alembic (`DOCUMIND_DB_SCHEMA=smartged alembic upgrade head --sql`) : Alembic reste la source de vérité, les migrations suivantes s'appliquent avec `alembic upgrade head`.

## 2. Activer le rôle applicatif (une seule fois, hors Git)

```sql
ALTER ROLE smartged_app WITH LOGIN PASSWORD '<mot-de-passe-fort>';
```

> Ne connectez jamais l'API avec le rôle `postgres` : sur Supabase il contourne la RLS.

## 3. Configurer le backend

Utilisez la chaîne **Session pooler** (port 5432) ou la connexion directe — pas le *Transaction pooler* (6543), incompatible avec les paramètres de session utilisés par la RLS.

```env
DOCUMIND_DATABASE_URL=postgresql+psycopg://smartged_app.<project-ref>:<mot-de-passe>@aws-0-<region>.pooler.supabase.com:5432/postgres
DOCUMIND_DB_SCHEMA=smartged
```

Les migrations futures se lancent avec un rôle propriétaire (`postgres`) :

```bash
DOCUMIND_DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<mdp>@...:5432/postgres \
DOCUMIND_DB_SCHEMA=smartged alembic upgrade head
```

puis `GRANT` automatiques grâce aux `DEFAULT PRIVILEGES`.

## 4. Premier client

```bash
python -m app.cli create-tenant --name "Mon entreprise" --slug mon-entreprise \
  --admin-email admin@mon-entreprise.com --admin-password '<mdp>'
```
