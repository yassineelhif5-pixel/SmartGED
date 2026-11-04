# Configuration OCR & IA

## OCR (disponible)

| Variable | Valeur | Effet |
|---|---|---|
| `DOCUMIND_OCR_PROVIDER` | `tesseract` (défaut) / `none` | Moteur utilisé pour les images et pages scannées |
| `DOCUMIND_OCR_LANGUAGES` | `fra+eng` | Langues Tesseract (seules celles installées sont utilisées) |
| `DOCUMIND_OCR_MIN_TEXT_CHARS_PER_PAGE` | `40` | En dessous, une page PDF est considérée comme scannée et passée à l'OCR |

Ajouter un fournisseur (Azure AI Document Intelligence, Google Document AI, AWS Textract) : implémenter `OcrProvider.ocr_image()` dans `app/ocr/engine.py` et l'enregistrer dans `get_ocr_provider()`. Le pipeline, le stockage des pages (`ocr_pages`, avec boîtes englobantes) et l'interface n'ont pas à changer.

## IA (phase 3)

Le registre `app/ai/registry.py` renvoie aujourd'hui `None` : les étapes *classification* et *extraction* sont enregistrées `not_configured`. La phase 3 ajoute les fournisseurs (OpenAI, Azure OpenAI, Anthropic, Gemini, modèles locaux), les clés chiffrées par tenant, le Prompt Studio et le registre de consommation.

Les types documentaires préparent déjà l'IA : `classification_hints` par type, `ai_extraction_enabled` et `extraction_prompt` par champ, `requires_human_validation` pour les données financières et juridiques.
