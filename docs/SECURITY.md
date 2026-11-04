# Guide de sécurité

## Contrôles en place

| Menace | Contrôle |
|---|---|
| Accès inter-tenant | Tenant issu du JWT + vérification d'appartenance + RLS PostgreSQL forcée ; ids étrangers ⇒ 404 |
| Vol de session | JWT 15 min en mémoire ; refresh opaque (seul le SHA-256 est stocké) en cookie httpOnly, Secure, SameSite=strict, rotation à chaque usage ; rejeu ⇒ révocation de toutes les sessions |
| Force brute | Rate limit par IP et par e-mail (Redis), Argon2id, réponse et temps constants si l'utilisateur n'existe pas |
| Escalade de privilèges | Permissions vérifiées côté serveur sur chaque route ; un rôle ne peut accorder que des permissions détenues ; le dernier Tenant Admin ne peut être retiré |
| Upload malveillant | Liste blanche d'extensions, contrôle par signature binaire, rejet des macros Office, taille max, nom de fichier assaini, antivirus ClamAV, quarantaine |
| Injection SQL | ORM paramétré exclusivement ; `LIKE` échappé |
| Traversée de chemin | Clés de stockage générées par le serveur ; garde `resolve()` sur le stockage local |
| Falsification d'audit | Trigger PostgreSQL bloquant UPDATE/DELETE + chaîne SHA-256 vérifiable (`/audit/verify`) |
| XSS / clickjacking | React (échappement), CSP stricte, `X-Frame-Options`, `nosniff` ; aperçus servis en blob |
| Secrets | Variables d'environnement uniquement ; refus de démarrer en UAT/PROD avec la clé par défaut |

## Recommandations de production

- `DOCUMIND_SECRET_KEY` ≥ 32 octets aléatoires, stockée dans Azure Key Vault / AWS Secrets Manager.
- PostgreSQL : rôle applicatif distinct du rôle de migration, chiffrement au repos, PITR.
- Stockage : chiffrement côté serveur (activé pour S3), versioning du bucket, accès privé uniquement.
- Activer ClamAV (`--profile antivirus`) ; le pipeline signale `not_configured` sinon.
- Terminer TLS au load balancer, HSTS est envoyé automatiquement en UAT/PROD.
