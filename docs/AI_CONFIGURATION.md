# Configuration OCR & IA

## OCR (disponible)

| Variable | Valeur | Effet |
|---|---|---|
| `DOCUMIND_OCR_PROVIDER` | `tesseract` (défaut) / `none` | Moteur utilisé pour les images et pages scannées |
| `DOCUMIND_OCR_LANGUAGES` | `fra+eng` | Langues Tesseract (seules celles installées sont utilisées) |
| `DOCUMIND_OCR_MIN_TEXT_CHARS_PER_PAGE` | `40` | En dessous, une page PDF est considérée comme scannée et passée à l'OCR |

Ajouter un fournisseur (Azure AI Document Intelligence, Google Document AI, AWS Textract) : implémenter `OcrProvider.ocr_image()` dans `app/ocr/engine.py` et l'enregistrer dans `get_ocr_provider()`. Le pipeline, le stockage des pages (`ocr_pages`, avec boîtes englobantes) et l'interface n'ont pas à changer.

## IA (disponible depuis la v0.4)

### Fournisseurs (Administration → Intelligence IA → Fournisseurs)

| Type | Endpoint | Authentification |
|---|---|---|
| Anthropic (Claude) | `https://api.anthropic.com/v1/messages` (`anthropic-version: 2026-10-21`) | `x-api-key` |
| OpenAI | `https://api.openai.com/v1/chat/completions` | Bearer |
| Azure OpenAI | `<endpoint>/openai/deployments/<déploiement>/chat/completions?api-version=…` | `api-key` |
| Google Gemini | `…/v1beta/models/<modèle>:generateContent` | `x-goog-api-key` |
| Compatible OpenAI (Ollama, vLLM, LM Studio, Mistral…) | URL fournie | clé facultative |

- Clés chiffrées en base (Fernet ; clé `DOCUMIND_ENCRYPTION_KEY`, sinon dérivée de `DOCUMIND_SECRET_KEY`), jamais renvoyées à l'interface (seuls les 4 derniers caractères).
- 3 tentatives avec attente exponentielle sur 408/409/429/5xx, puis bascule sur le **fournisseur de secours**.
- Bouton « Tester » : aller-retour réel avec le fournisseur, compté dans la consommation.

### Pipeline

1. **Classification** : le modèle choisit parmi les types documentaires actifs (avec leurs « indices de classification »). Appliquée automatiquement si la confiance ≥ `ai.confidence_threshold` (0,85 par défaut) ; sinon le document passe « À valider » avec une suggestion affichée dans la visionneuse.
2. **Extraction** : champs dont « Extraction IA » est activé, avec la consigne propre à chaque champ. Chaque valeur porte confiance, page et texte source.

Garde-fous anti-hallucination : `null` exigé si absent, revalidation par les règles du champ, texte source vérifié dans l'OCR (confiance divisée par 2 sinon), valeurs manuelles/validées/issues d'un référentiel jamais écrasées, document encadré par `<document>` et neutralisé contre l'injection de consignes, validation humaine obligatoire des champs obligatoires et financiers.

### Découpage des lots (Document Splitting Engine)

Après la détection de langue, un PDF de plusieurs pages passe par l'étape `splitting` :

- **Analyse de structure** (toujours active, sans IA) : numérotation « Page 1/N » qui repart, en-têtes avec numéro (« FACTURE N° … », « BON DE COMMANDE … »), changement de référence, pages blanches de séparation. Une page « 2/3 » n'ouvre jamais un document.
- **IA** (si un fournisseur est configuré) : prompt `document_splitting` modifiable dans le Prompt Studio. Une réponse incohérente (chevauchement, pages hors limites) est rejetée et l'analyse de structure prend le relais.

Si plusieurs documents sont détectés, le traitement s'arrête en « À valider » jusqu'à la revue (Document → « Vérifier le découpage »). Paramètres d'organisation :

| Clé | Défaut | Effet |
|---|---|---|
| `splitting.enabled` | `true` | Désactive l'étape |
| `splitting.ai_enabled` | `true` | Analyse de structure seule |
| `splitting.auto_apply_threshold` | absent | Applique sans revue si la confiance minimale des coupures atteint ce seuil |

### Recherche sémantique et Lina (phase 4)

- Chaque document est découpé en passages (~1 200 caractères, par page) à l'étape `indexing` : la recherche par mots-clés et Lina fonctionnent sans IA d'embeddings.
- Pour la recherche par le sens, renseignez **Modèle d'embeddings** sur un fournisseur OpenAI, Azure OpenAI (nom du déploiement), Gemini ou compatible OpenAI (ex. `nomic-embed-text` avec Ollama). Anthropic n'a pas d'API d'embeddings. Cliquez ensuite sur **Réindexer**.
- Paramètre d'organisation `search.min_similarity` (défaut 0,25) : en dessous, un passage n'est pas considéré comme pertinent.
- Lina utilise le prompt `lina_answer` (modifiable dans le Prompt Studio ; `{{sources}}` doit rester entre `<documents>` et `</documents>`). Les citations renvoyées par le modèle sont vérifiées ; consommation enregistrée sous `lina` et `embedding`.
- Base auto-hébergée : l'extension doit être créée une fois par un superutilisateur : `CREATE SCHEMA IF NOT EXISTS extensions; CREATE EXTENSION vector WITH SCHEMA extensions;`

### Prompt Studio

Consignes plateforme (v1) pour `classification`, `metadata_extraction`, `document_summary`. Une organisation crée ses versions, les **teste sur un vrai document** (tokens, latence, coût), puis les publie (publication refusée sans test réussi, sauf `force`, tracé dans l'audit). « Revenir à la plateforme » annule la personnalisation.

### Consommation et crédits

Chaque appel (succès ou échec) est inscrit dans `ai_usage_events` avec une clé d'idempotence (pas de double comptage). Coût = tarifs versionnés `ai_model_prices` (USD / million de tokens, ajoutés par le Super Admin via `POST /platform/ai/prices`). 1 crédit = 0,001 $ ; sans tarif, 1 crédit / 1 000 tokens. Quota mensuel par plan (`ai_credits_monthly`) : au-delà, les étapes IA sont ignorées et signalées.
