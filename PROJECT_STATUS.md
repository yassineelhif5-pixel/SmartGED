# PROJECT_STATUS — SmartGED (DocuMind AI)

_Dernière mise à jour : 24 novembre 2026 — v0.6 : phase 4 (recherche hybride + assistant Lina avec sources)_

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
| Fournisseurs IA (Anthropic, OpenAI, Azure OpenAI, Gemini, compatible OpenAI), clés chiffrées, retry + secours | ✅ | ✅ | ✅ formats réels simulés |
| Classification automatique (seuil, suggestion pour l'humain) | ✅ | ✅ bandeau de suggestion | ✅ |
| Extraction des métadonnées (confiance, page, texte source, garde-fous) | ✅ | ✅ badges IA | ✅ |
| Prompt Studio : versions, test avant publication, rollback | ✅ | ✅ | ✅ |
| Registre de consommation idempotent, tarifs versionnés, quota de crédits | ✅ | ✅ onglet Consommation | ✅ |
| Résumé de document (Lina) | ✅ | ✅ | ✅ |
| Découpage des lots PDF : détection structure + IA, revue page par page, documents enfants liés, original archivé | ✅ | ✅ écran de découpage | ✅ |
| Index de connaissances : passages (chunks) par page, plein texte, embeddings pgvector si configurés, réindexation | ✅ | ✅ carte « Index de connaissances » | ✅ |
| Recherche hybride (mots-clés + sens, fusion RRF, seuil de similarité) | ✅ | ✅ recherche globale instantanée | ✅ |
| Assistant Lina (RAG) : réponses sourcées, citations vérifiées, périmètre document / dossier, historique | ✅ | ✅ page Lina + « Demander à Lina » | ✅ |
| Schéma PostgreSQL dédié (`DOCUMIND_DB_SCHEMA`) + migrations SQL Supabase | ✅ | — | ✅ base vierge |

## Tests

- Backend : **61/61** (dont 9 sur l'IA, 9 sur les vues et les référentiels, 9 sur le découpage, 7 sur la recherche et Lina)
- Ancien total backend : 27/27 (`pytest`) sur PostgreSQL réel — dont 7 tests d'isolation inter-tenant (lecture, écriture, RLS sans filtre applicatif, en-tête forgé, audit immuable).
- Frontend : **10/10** (Vitest), `tsc` strict sans erreur, build de production OK.
- Parcours bout-en-bout vérifié dans Chrome headless avec worker Celery réel : connexion → dépôt de 3 fichiers (PDF texte, PDF scanné, texte) → OCR → recherche sur le texte du PDF scanné → saisie et validation des métadonnées → publication. Aucune erreur console.
- Découpage vérifié dans Chrome headless : lot de 7 pages (2 factures, 1 bon de commande, 1 contrat, 1 page blanche) → 4 documents proposés, appliqués, puis classés par le pipeline.
- Lina vérifiée dans Chrome headless : ajout d'un modèle d'embeddings, réindexation (100 % vectorisé), recherche globale hybride, question → réponse avec 2 sources cliquables.
- Lint `ruff` : OK.

## Problèmes connus / limites

- **Supabase provisionné** (projet `gfndyqtkvfcdmnpugwdk`, révision 0007, 43 tables, pgvector dans le schéma `extensions`). Isolation vérifiée en tant que `smartged_app`, advisors sécurité sans alerte. Reste à activer le login de `smartged_app` avec votre mot de passe et à brancher l'API dessus.
- Les vues partagées ne mémorisent pas encore la sélection de colonnes du tableau.
- **IA testée sans vraie clé** : adaptateurs vérifiés sur les formats de réponse officiels (transport HTTP simulé) et parcours navigateur avec un LLM local de test. Un essai avec une clé réelle reste à faire.
- Recherche vectorielle exacte (pas d'index HNSW) : adaptée jusqu'à quelques centaines de milliers de passages par organisation ; un index par dimension sera ajouté au besoin.
- Lina n'est pas encore en streaming (réponse affichée d'un bloc).
- Découpage : PDF uniquement (pas les TIFF multipages). La détection IA lit un extrait de chaque page (900 caractères), pas la page entière.
- Pas de tarifs IA préremplis : à saisir par le Super Admin (sinon 1 crédit / 1 000 tokens).

- Pas encore de SSO (Entra ID, SAML), MFA ni envoi d'e-mails d'invitation (phase 7 / notifications).
- L'aperçu TIFF et Office n'est pas rendu dans le navigateur (le texte extrait reste consultable).
- Le rate limiter retombe en mémoire si Redis est indisponible (à proscrire en production).
- Les quotas de crédits IA sont initialisés mais pas encore consommés (phase 7, module Crédits).
- Permissions au niveau dossier/document (ACL fines) : modèle prévu, non implémenté (phase 2.5).

## Décisions techniques

- **ADR-007** Les attributs d'objets métier réutilisent `metadata_definitions` (un champ appartient soit à un type documentaire, soit à un type d'objet — contrainte `single_owner`) : un seul moteur de validation et un seul designer.
- **ADR-008** Convention d'alimentation : même nom technique, ou `{code_type}_name` / `{code_type}_code` ; jamais d'écrasement sans `overwrite`, valeurs marquées `source = object` et toujours soumises à validation humaine.
- **ADR-010** Adaptateurs IA en HTTP brut (httpx) plutôt que SDK : moteur neutre vis-à-vis des fournisseurs, testable sur les formats réels.
- **ADR-011** Prompts plateforme partagés (`tenant_id` NULL, lisibles par tous via RLS) + surcharges par organisation ; publication conditionnée à un test réussi.
- **ADR-012** Un découpage n'est jamais appliqué sans validation humaine, sauf si l'organisation fixe `splitting.auto_apply_threshold`. Le lot d'origine est archivé, jamais supprimé ; les enfants réutilisent son OCR.
- **ADR-013** Toute récupération (recherche, Lina) passe par `visible_documents()` : point unique où brancher les ACL dossier/document. Sans passage pertinent, Lina répond « rien trouvé » sans appeler le modèle.
- **ADR-014** Colonne vectorielle sans dimension fixe + `embedding_model` par passage : chaque organisation choisit son modèle ; un changement de modèle impose une réindexation.
- **ADR-009** Sur Supabase, schéma `smartged` non exposé à PostgREST et rôle `smartged_app` NOBYPASSRLS ; `postgres` réservé aux migrations.

- **ADR-001** Monolithe modulaire FastAPI (pas de microservices prématurés).
- **ADR-002** Double isolation tenant : filtres applicatifs + RLS PostgreSQL forcée ; bypass uniquement pour les opérations plateforme, jamais piloté par l'entrée utilisateur.
- **ADR-003** Identité globale (`users`) + appartenances (`user_tenants`) : un utilisateur peut appartenir à plusieurs organisations.
- **ADR-004** Recherche plein texte via colonne `tsvector` générée (config `simple`, multilingue) ; pgvector pour la phase 4.
- **ADR-005** Pipeline à étapes persistées (`processing_jobs`) uniques par (document, version, étape) pour l'idempotence.
- **ADR-006** Aucune simulation : une capacité absente est enregistrée `not_configured`.

## Prochaines étapes

1. Brancher une vraie clé IA et calibrer le seuil de confiance sur des documents réels.
2. Phase 5 : workflows de validation configurables (étapes, délais, relances, notifications).
3. Brancher l'API sur Supabase (login `smartged_app`, Session pooler).
4. ACL au niveau dossier / document.
