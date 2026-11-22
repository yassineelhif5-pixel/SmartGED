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

### Prompt Studio

Consignes plateforme (v1) pour `classification`, `metadata_extraction`, `document_summary`. Une organisation crée ses versions, les **teste sur un vrai document** (tokens, latence, coût), puis les publie (publication refusée sans test réussi, sauf `force`, tracé dans l'audit). « Revenir à la plateforme » annule la personnalisation.

### Consommation et crédits

Chaque appel (succès ou échec) est inscrit dans `ai_usage_events` avec une clé d'idempotence (pas de double comptage). Coût = tarifs versionnés `ai_model_prices` (USD / million de tokens, ajoutés par le Super Admin via `POST /platform/ai/prices`). 1 crédit = 0,001 $ ; sans tarif, 1 crédit / 1 000 tokens. Quota mensuel par plan (`ai_credits_monthly`) : au-delà, les étapes IA sont ignorées et signalées.
