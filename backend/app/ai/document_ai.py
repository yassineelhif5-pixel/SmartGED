"""Document intelligence steps: classification and metadata extraction.

Anti-hallucination guarantees:
* the model is instructed to return null rather than guess;
* every extracted value is re-validated by the field's rules (type, pattern, list…);
* the quoted ``source_text`` must really appear in the OCR text, otherwise confidence is halved
  and the mismatch is reported;
* values typed, validated or filled from a business object by a human are never overwritten;
* AI values always start as "not validated" — required, financial and legal fields go through
  the human validation centre before publication.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.models import (
    Document,
    DocumentMetadataValue,
    DocumentType,
    MetadataDataType,
    OcrPage,
    StepStatus,
)
from app.services import ai_service, metadata_service

PROTECTED_SOURCES = {"manual", "object", "default"}
NOT_EXTRACTABLE = {MetadataDataType.reference, MetadataDataType.calculated}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[\s ]+", " ", text).strip()


def document_pages(db: Session, doc: Document) -> list[tuple[int, str]]:
    rows = db.execute(select(OcrPage.page_number, OcrPage.text).where(
        OcrPage.document_id == doc.id, OcrPage.version_number == doc.current_version).order_by(OcrPage.page_number)).all()
    return [(n, t) for n, t in rows] or ([(1, doc.content_text)] if doc.content_text else [])


def classify(db: Session, doc: Document, *, key: str) -> dict[str, Any]:
    types = list(db.scalars(select(DocumentType).where(DocumentType.tenant_id == doc.tenant_id,
                                                       DocumentType.is_active.is_(True))))
    if not types:
        return {"skipped": "no_document_types"}
    catalogue = "\n".join(f"- {t.code} — {t.name} — {(t.classification_hints or t.description or '').strip()}"
                          for t in types)
    content = ai_service.build_document_content(document_pages(db, doc), get_settings().ai_max_document_chars)
    result = ai_service.run_prompt(
        db, doc.tenant_id, prompt_code="classification", feature="classification", idempotency_key=key,
        document_id=doc.id, variables={"document_content": content, "document_types": catalogue,
                                       "file_name": doc.original_file_name, "language": doc.language or "inconnue"})
    data = result.data or {}
    code = data.get("document_type")
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
    match = next((t for t in types if t.code == code), None)
    threshold = float(ai_service.get_setting(db, doc.tenant_id, "ai.confidence_threshold", 0.85))
    out = {"suggested_type": match.code if match else None, "suggested_type_id": str(match.id) if match else None,
           "suggested_type_name": match.name if match else None, "confidence": confidence,
           "reason": str(data.get("reason") or "")[:500], "threshold": threshold, "model": result.completion.model,
           "tokens": result.completion.input_tokens + result.completion.output_tokens, "credits": result.credits,
           "parsed": result.data is not None}
    doc.classification_confidence = confidence if match else None
    if match and confidence >= threshold:
        doc.document_type_id = match.id
        doc.classification_status = StepStatus.completed
        out["applied"] = True
        db.flush()
        db.refresh(doc, ["document_type"])
    else:
        doc.classification_status = StepStatus.pending  # a human picks the type; the suggestion is kept
        out["applied"] = False
    return out


def extract(db: Session, doc: Document, *, key: str) -> dict[str, Any]:
    dtype = doc.document_type
    if dtype is None:
        return {"skipped": "no_document_type"}
    fields = [f for f in dtype.fields if f.ai_extraction_enabled and f.data_type not in NOT_EXTRACTABLE]
    if not fields:
        return {"skipped": "no_extractable_field"}
    schema = "\n".join(
        f"- {f.technical_name} — {f.display_name} — {f.data_type.value}"
        + (f" (valeurs : {', '.join(f.allowed_values)})" if f.allowed_values else "")
        + (f" — {f.extraction_prompt}" if f.extraction_prompt else "")
        for f in fields)
    pages = document_pages(db, doc)
    content = ai_service.build_document_content(pages, get_settings().ai_max_document_chars)
    rules = ai_service.get_setting(db, doc.tenant_id, "ai.business_rules", "") or "aucune"
    result = ai_service.run_prompt(
        db, doc.tenant_id, prompt_code="metadata_extraction", feature="metadata_extraction", idempotency_key=key,
        document_id=doc.id, variables={"document_content": content, "document_type": dtype.name,
                                       "metadata_schema": schema, "language": doc.language or "inconnue",
                                       "business_rules": rules})
    if result.data is None or not isinstance(result.data.get("fields"), dict):
        raise RuntimeError("The AI response is not valid JSON with a 'fields' object")
    raw_fields: dict[str, Any] = result.data["fields"]
    haystack = _norm(" ".join(t for _, t in pages))
    existing = {v.definition_id: v for v in db.scalars(
        select(DocumentMetadataValue).where(DocumentMetadataValue.document_id == doc.id))}
    extracted, empty, rejected, protected, unverified = [], [], [], [], []
    confidences: list[float] = []
    for f in fields:
        item = raw_fields.get(f.technical_name)
        if not isinstance(item, dict) or item.get("value") in (None, "", []):
            empty.append(f.technical_name)
            continue
        row = existing.get(f.id)
        if row is not None and (row.validation_status == StepStatus.completed
                                or (row.source in PROTECTED_SOURCES and row.value not in (None, "", []))):
            protected.append(f.technical_name)
            continue
        try:
            value = metadata_service.coerce_value(f, item.get("value"))
        except ValidationFailed as exc:
            rejected.append({"field": f.technical_name, "reason": exc.message})
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.5)))
        except (TypeError, ValueError):
            confidence = 0.5
        source_text = str(item["source_text"])[:2000] if item.get("source_text") else None
        if not source_text:
            confidence = min(confidence, 0.5)
        elif _norm(source_text) not in haystack:
            confidence = round(confidence * 0.5, 4)
            unverified.append(f.technical_name)
        page = item.get("page")
        page = page if isinstance(page, int) and 1 <= page <= max(len(pages), 1) else None
        if row is None:
            row = DocumentMetadataValue(tenant_id=doc.tenant_id, document_id=doc.id, definition_id=f.id)
            db.add(row)
        row.value, row.source, row.confidence = value, "ai", confidence
        row.source_page, row.source_text = page, source_text
        row.validation_status, row.validated_by, row.validated_at = StepStatus.pending, None, None
        extracted.append(f.technical_name)
        confidences.append(confidence)
    db.flush()
    return {"extracted": extracted, "empty": empty, "rejected": rejected, "protected": protected,
            "unverified_source": unverified, "schema_version": dtype.schema_version,
            "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
            "model": result.completion.model, "credits": result.credits,
            "tokens": result.completion.input_tokens + result.completion.output_tokens}


def summarize(db: Session, doc: Document, *, user_id: uuid.UUID) -> dict[str, Any]:
    content = ai_service.build_document_content(document_pages(db, doc), get_settings().ai_max_document_chars)
    result = ai_service.run_prompt(
        db, doc.tenant_id, prompt_code="document_summary", feature="document_summary",
        idempotency_key=f"summary:{doc.id}:v{doc.current_version}:{uuid.uuid4()}", document_id=doc.id,
        user_id=user_id, variables={"document_content": content, "language": doc.language or "inconnue",
                                    "document_type": doc.document_type.name if doc.document_type else "inconnu"})
    return {"result": result.data, "raw": None if result.data else result.text, "model": result.completion.model,
            "credits": result.credits}


def all_variables(db: Session, doc: Document) -> dict[str, Any]:
    """Every variable a prompt template may use, for the Prompt Testing Studio."""
    types = list(db.scalars(select(DocumentType).where(DocumentType.tenant_id == doc.tenant_id,
                                                       DocumentType.is_active.is_(True))))
    dtype = doc.document_type
    fields = [f for f in (dtype.fields if dtype else []) if f.ai_extraction_enabled and f.data_type not in NOT_EXTRACTABLE]
    return {
        "document_content": ai_service.build_document_content(document_pages(db, doc), get_settings().ai_max_document_chars),
        "document_types": "\n".join(f"- {t.code} — {t.name} — {(t.classification_hints or '').strip()}" for t in types),
        "document_type": dtype.name if dtype else "inconnu",
        "metadata_schema": "\n".join(f"- {f.technical_name} — {f.display_name} — {f.data_type.value}"
                                     + (f" — {f.extraction_prompt}" if f.extraction_prompt else "") for f in fields),
        "file_name": doc.original_file_name,
        "language": doc.language or "inconnue",
        "tenant_id": str(doc.tenant_id),
        "confidence_threshold": str(ai_service.get_setting(db, doc.tenant_id, "ai.confidence_threshold", 0.85)),
        "business_rules": ai_service.get_setting(db, doc.tenant_id, "ai.business_rules", "") or "aucune",
    }
