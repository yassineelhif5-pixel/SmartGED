# PROJECT_STATUS — SmartGED (DocuMind AI)

_Dernière mise à jour : 22 novembre 2026 — v0.3 : vues partagées/personnelles, référentiels, préparation Supabase_

Dépôt : https://github.com/yassineelhif5-pixel/SmartGED (branches `main`, `develop`)

## Modules développés

| Module | Backend | Frontend | Tests |
|---|---|---|---|
| Configuration, logs JSON corrélés, erreurs normalisées | ✅ | — | ✅ |
| Multi-tenant (tenant_id + RLS FORCE sur 20 tables) | ✅ | ✅ sélecteur d'organisation | ✅ API + RLS |
| Provisioning tenant (plan, quotas, modules, rôles, admin, dossiers, types de départ) | ✅ | ✅ Pilot | ✅ |
| Suspension / réactivation de tenant | ✅ | ✅ | ✅ |
| Authentification (Argon2id, JWT + refresh rotatif, détection de rejeu, rate limit) | ✅ | ✅ | ✅ |
| RBAC (permissions, rôles système et personnalisés, anti-escalade) | ✅ | ✅ | ✅ |
| Utilisateurs (ajout, invitation, rôles, désactivation, retrait, garde dernier admin) | ✅ | ✅ | ✅ |
| Dossiers (arborescence, renommage, déplacement anti-cycle, suppression → corbeille) | ✅ | ✅ | ✅ |
| Documents (upload sécurisé, doublons, versions, check-in/out, corbeille, purge, copie, relations, tags) | ✅ | ✅ | ✅ |
| Stockage objet (local dev, S3, Azure Blob) | ✅ | — | ✅ local |
| Pipeline asynchrone Celery (retry, DLQ, files prioritaires, étapes idempotentes) | ✅ | ✅ centre de traitement | ✅ |
| OCR (couche texte PDF + Tesseract, confiance, positions des mots) | ✅ | ✅ onglet Texte | ✅ OCR réel |
| Antivirus ClamAV (INSTREAM) | ✅ | ✅ statut | ⚠️ non testé sans démon |
| Types documentaires & Metadata Designer (versioning de schéma) | ✅ | ✅ | ✅ |
| Validation humaine des métadonnées | ✅ | ✅ centre de validation | ✅ |
| Recherche plein texte + filtres (métadonnées, tags, dates, statut) | ✅ | ✅ | ✅ |
| Tableau de bord (KPI réels) | ✅ | ✅ | ✅ |
| Audit append-only chaîné + vérification + export CSV | ✅ | ✅ | ✅ |
| Vues de documents partagées (admin, défaut organisation) et personnelles (défaut utilisateur) | ✅ | ✅ barre de vues | ✅ |
| Filtres avancés (dates, tag, mes documents, objet lié, valeurs de métadonnées) | ✅ | ✅ | ✅ |
| Référentiels : types d'objets configurables + fiches (fournisseur, client, projet…) | ✅ | ✅ | ✅ |
| Liens document ↔ objet, champ « référence », alimentation automatique des métadonnées | ✅ | ✅ onglet Objets liés | ✅ |
| Schéma PostgreSQL dédié (`DOCUMIND_DB_SCHEMA`) + migrations SQL Supabase | ✅ | — | ✅ base vierge |

## Tests

- Backend : **36/36** (dont 9 sur les vues et les référentiels)
- Ancien total backend : 27/27 (`pytest`) sur PostgreSQL réel — dont 7 tests d'isolation inter-tenant (lecture, écriture, RLS sans filtre applicatif, en-tête forgé, audit immuable).
- Frontend : **7/7** (Vitest), `tsc` strict sans erreur, build de production OK.
- Parcours bout-en-bout vérifié dans Chrome headless avec worker Celery réel : connexion → dépôt de 3 fichiers (PDF texte, PDF scanné, texte) → OCR → recherche sur le texte du PDF scanné → saisie et validation des métadonnées → publication. Aucune erreur console.
- Lint `ruff` : OK.

## Problèmes connus / limites

- **Supabase non encore provisionné** : la limite de 2 projets gratuits du compte est atteinte. Les migrations sont prêtes dans `supabase/` ; à appliquer dès qu'une place est libérée.
- Les vues partagées ne mémorisent pas encore la sélection de colonnes du tableau.

- Pas encore de SSO (Entra ID, SAML), MFA ni envoi d'e-mails d'invitation (phase 7 / notifications).
- L'aperçu TIFF et Office n'est pas rendu dans le navigateur (le texte extrait reste consultable).
- Le rate limiter retombe en mémoire si Redis est indisponible (à proscrire en production).
- Les quotas de crédits IA sont initialisés mais pas encore consommés (phase 7, module Crédits).
- Permissions au niveau dossier/document (ACL fines) : modèle prévu, non implémenté (phase 2.5).

## Décisions techniques

- **ADR-007** Les attributs d'objets métier réutilisent `metadata_definitions` (un champ appartient soit à un type documentaire, soit à un type d'objet — contrainte `single_owner`) : un seul moteur de validation et un seul designer.
- **ADR-008** Convention d'alimentation : même nom technique, ou `{code_type}_name` / `{code_type}_code` ; jamais d'écrasement sans `overwrite`, valeurs marquées `source = object` et toujours soumises à validation humaine.
- **ADR-009** Sur Supabase, schéma `smartged` non exposé à PostgREST et rôle `smartged_app` NOBYPASSRLS ; `postgres` réservé aux migrations.

- **ADR-001** Monolithe modulaire FastAPI (pas de microservices prématurés).
- **ADR-002** Double isolation tenant : filtres applicatifs + RLS PostgreSQL forcée ; bypass uniquement pour les opérations plateforme, jamais piloté par l'entrée utilisateur.
- **ADR-003** Identité globale (`users`) + appartenances (`user_tenants`) : un utilisateur peut appartenir à plusieurs organisations.
- **ADR-004** Recherche plein texte via colonne `tsvector` générée (config `simple`, multilingue) ; pgvector pour la phase 4.
- **ADR-005** Pipeline à étapes persistées (`processing_jobs`) uniques par (document, version, étape) pour l'idempotence.
- **ADR-006** Aucune simulation : une capacité absente est enregistrée `not_configured`.

## Prochaines étapes (Phase 3 — AI Intelligence)

1. Tables `ai_providers`, `ai_models`, `ai_configurations` (clés chiffrées par tenant), adaptateurs OpenAI / Azure OpenAI / Anthropic / Gemini / local.
2. Prompt Management Studio (prompts versionnés, variables, test avant publication).
3. Classification automatique + extraction des métadonnées avec score de confiance, page et texte source.
4. Registre `ai_usage_events` idempotent (pas de double comptage en retry) + crédits.
5. Document Splitting Engine et interface de validation du découpage.
6. ACL au niveau dossier / document.
