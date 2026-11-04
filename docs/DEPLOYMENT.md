# Guide de déploiement

## Environnements

| Env | `DOCUMIND_ENVIRONMENT` | Stockage | Notes |
|---|---|---|---|
| DEV | `dev` | local | `DOCUMIND_SECURE_COOKIES=false` possible |
| TEST | `test` | local | CI GitHub Actions |
| UAT | `uat` | S3 / Azure Blob | clé secrète obligatoire, HSTS |
| PROD | `prod` | S3 / Azure Blob | stockage local interdit au démarrage |

## Variables principales

Voir `backend/.env.example`. Toutes préfixées `DOCUMIND_`.

## Procédure

1. Construire les images : `docker build -t documind-api backend` et `docker build -t documind-web frontend`.
2. Base : PostgreSQL 16 avec extension `vector` disponible (image `pgvector/pgvector:pg16` ou Azure Database for PostgreSQL Flexible Server).
3. Le conteneur API exécute `alembic upgrade head` au démarrage (migrations idempotentes) puis le bootstrap (catalogue de permissions, plans, Super Admin).
4. Lancer au moins un worker Celery (même image, commande `celery … worker`).
5. Smoke test : `GET /api/v1/health/ready` doit renvoyer `database: ok`, `redis: ok` et la liste des capacités.

## Azure (cible)

- Azure Container Apps : `api`, `worker` (scale sur la longueur de file Redis), `web`.
- Azure Database for PostgreSQL Flexible Server, Azure Cache for Redis, Azure Blob Storage (`DOCUMIND_STORAGE_PROVIDER=azure_blob`).
- Key Vault pour les secrets, Application Insights pour les logs JSON.

## Sauvegarde et restauration

- PostgreSQL : PITR 35 jours + export logique quotidien.
- Stockage objet : versioning + réplication géographique.
- Restauration : restaurer la base à T, puis le stockage à T (les clés étant adressées par contenu, les objets plus récents sont ignorés sans risque).
