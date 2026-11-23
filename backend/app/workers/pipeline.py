"""Document intelligence pipeline.

Steps are idempotent and individually tracked in ``processing_jobs`` (unique
per document / version / step). Re-running the pipeline skips completed steps
unless ``force=True``. Each step runs in its own transaction so progress is
visible to the UI in real time and a failure never loses earlier work.

Steps:
  antivirus → text_extraction (text layer + Tesseract OCR) → language →
  splitting (multi-document PDF detection; pauses for human review) → classification (AI) → metadata_extraction (AI) → indexing → publication

The AI steps run through the tenant's configured provider (app.ai). Without one
they are recorded as ``not_configured`` — never faked.
"""

from __future__ import annotations

import contextvars
import shutil
import tempfile
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, tenant_id_var
from app.database.session import session_scope
from app.models import Document, DocumentStatus, OcrPage, ProcessingJob, StepStatus
from app.ocr.engine import OcrNotConfigured, detect_language, extract_text
from app.security.antivirus import scan_file
from app.storage.providers import get_storage

log = get_logger(__name__)
_current_attempt: contextvars.ContextVar[int] = contextvars.ContextVar("pipeline_attempt", default=1)

STEPS = ["antivirus", "text_extraction", "language", "splitting", "classification", "metadata_extraction", "indexing", "publication"]


class StepSkip(Exception):
    def __init__(self, status: StepStatus, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class PipelineHalt(Exception):
    """Stop the pipeline (e.g. infected file); not a technical failure."""


class PipelinePause(Exception):
    """The step completed but a human decision is needed before the next steps (e.g. split review)."""

    def __init__(self, result: dict, reason: str) -> None:
        super().__init__(reason)
        self.result = result
        self.reason = reason


def _job(db: Session, doc: Document, step: str) -> ProcessingJob:
    job = db.scalar(select(ProcessingJob).where(
        ProcessingJob.document_id == doc.id, ProcessingJob.version_number == doc.current_version,
        ProcessingJob.step == step))
    if job is None:
        job = ProcessingJob(tenant_id=doc.tenant_id, document_id=doc.id, version_number=doc.current_version, step=step)
        db.add(job)
        db.flush()
    return job


def _materialise(doc: Document, workdir: Path) -> Path:
    target = workdir / f"source.{doc.extension or 'bin'}"
    storage = get_storage(doc.storage_provider)
    with storage.open(doc.storage_path) as src, open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return target


# --------------------------------------------------------------------- steps
def step_antivirus(db: Session, doc: Document, path: Path) -> dict:
    result = scan_file(path)
    if result.status == "infected":
        doc.scan_status = StepStatus.failed
        doc.status = DocumentStatus.rejected
        raise PipelineHalt(f"Malware detected: {result.signature}")
    if result.status == "not_configured":
        doc.scan_status = StepStatus.not_configured
        raise StepSkip(StepStatus.not_configured, result.detail or "Antivirus not configured")
    if result.status == "error":
        raise RuntimeError(f"Antivirus error: {result.detail}")
    doc.scan_status = StepStatus.completed
    return {"result": "clean"}


def step_text_extraction(db: Session, doc: Document, path: Path) -> dict:
    doc.ocr_status = StepStatus.running
    db.flush()
    try:
        extraction = extract_text(path, doc.mime_type)
    except OcrNotConfigured as exc:
        doc.ocr_status = StepStatus.not_configured
        raise StepSkip(StepStatus.not_configured, str(exc)) from exc
    db.execute(delete(OcrPage).where(OcrPage.document_id == doc.id, OcrPage.version_number == doc.current_version))
    for page in extraction.pages:
        db.add(OcrPage(tenant_id=doc.tenant_id, document_id=doc.id, version_number=doc.current_version,
                       page_number=page.page_number, text=page.text, method=page.method,
                       confidence=page.confidence, blocks=page.blocks))
    doc.content_text = extraction.full_text[:2_000_000] or None
    doc.page_count = len(extraction.pages) if doc.mime_type == "application/pdf" else (doc.page_count or 1)
    doc.ocr_status = StepStatus.completed
    confs = [p.confidence for p in extraction.pages if p.confidence is not None]
    return {"pages": len(extraction.pages), "ocr_used": extraction.ocr_used, "provider": extraction.provider,
            "chars": len(extraction.full_text), "avg_confidence": round(sum(confs) / len(confs), 4) if confs else None,
            "methods": sorted({p.method for p in extraction.pages})}


def step_language(db: Session, doc: Document, path: Path) -> dict:
    if not doc.content_text:
        raise StepSkip(StepStatus.skipped, "No text available")
    doc.language = detect_language(doc.content_text)
    return {"language": doc.language}


def step_splitting(db: Session, doc: Document, path: Path) -> dict:
    from app.services import split_service
    from app.services.ai_service import get_setting

    if doc.parent_document_id is not None:
        raise StepSkip(StepStatus.skipped, "Child of a split document")
    if not split_service.is_splittable(doc):
        raise StepSkip(StepStatus.skipped, "Single-page or non-PDF document")
    if not bool(get_setting(db, doc.tenant_id, "splitting.enabled", True)):
        raise StepSkip(StepStatus.skipped, "Splitting disabled for this organisation")
    detection = split_service.detect(db, doc, key=_ai_key(doc, "splitting"))
    proposal = split_service.save_proposal(db, doc, detection)
    result = {"method": detection.method, "segments": len(detection.segments), "confidence": detection.confidence,
              "separator_pages": detection.separator_pages, "proposal_id": str(proposal.id),
              "ai": detection.details.get("ai")}
    if not detection.is_multi:
        return result
    threshold = get_setting(db, doc.tenant_id, "splitting.auto_apply_threshold", None)
    if threshold is not None and detection.confidence is not None and detection.confidence >= float(threshold):
        children = split_service.apply_split(db, doc, user_id=None, segments=detection.segments, proposal=proposal)
        result["auto_applied"] = True
        result["children"] = [str(c.id) for c in children]
        raise PipelinePause(result, "auto_split")
    doc.status = DocumentStatus.pending_validation
    doc.validation_status = StepStatus.pending
    raise PipelinePause(result, "split_review")


def _ai_key(doc: Document, step: str) -> str:
    return f"pipeline:{doc.id}:v{doc.current_version}:{step}:a{_current_attempt.get()}"


def _run_ai(doc: Document, step: str, fn: Callable[..., dict], db: Session) -> dict:
    from app.core.errors import QuotaExceeded
    from app.services.ai_service import AINotConfigured

    try:
        return fn(db, doc, key=_ai_key(doc, step))
    except AINotConfigured as exc:
        raise StepSkip(StepStatus.not_configured, str(exc)) from exc
    except QuotaExceeded as exc:
        raise StepSkip(StepStatus.skipped, exc.message) from exc


def step_classification(db: Session, doc: Document, path: Path) -> dict:
    from app.ai.document_ai import classify

    if doc.document_type_id:
        doc.classification_status = StepStatus.completed
        raise StepSkip(StepStatus.skipped, "Document type set by the user")
    if not doc.content_text:
        raise StepSkip(StepStatus.skipped, "No text to classify")
    try:
        result = _run_ai(doc, "classification", classify, db)
    except StepSkip as skip:
        doc.classification_status = skip.status
        raise
    return result


def step_metadata_extraction(db: Session, doc: Document, path: Path) -> dict:
    from app.ai.document_ai import extract
    from app.services.ai_service import active_provider

    if active_provider(db, doc.tenant_id) is None:
        doc.ai_status = StepStatus.not_configured
        raise StepSkip(StepStatus.not_configured, "No active AI provider configured for this organisation")
    if doc.document_type_id is None:
        doc.ai_status = StepStatus.skipped
        raise StepSkip(StepStatus.skipped, "No document type: classify the document first")
    if not doc.content_text:
        doc.ai_status = StepStatus.skipped
        raise StepSkip(StepStatus.skipped, "No text to analyse")
    doc.ai_status = StepStatus.running
    db.flush()
    try:
        result = _run_ai(doc, "metadata_extraction", extract, db)
    except StepSkip as skip:
        doc.ai_status = skip.status
        raise
    doc.ai_status = StepStatus.completed
    return result


def step_indexing(db: Session, doc: Document, path: Path) -> dict:
    # Full-text index is a generated tsvector column → always consistent with content_text.
    return {"full_text": True, "vector": "phase_4"}


def step_publication(db: Session, doc: Document, path: Path) -> dict:
    from app.models import DocumentMetadataValue

    dtype = doc.document_type
    if dtype is None and doc.classification_status == StepStatus.pending:
        # The AI could not classify with enough confidence: a human must pick the type.
        doc.status = DocumentStatus.pending_validation
        doc.validation_status = StepStatus.pending
        return {"status": doc.status.value, "reason": "classification_needed"}
    must = [f for f in dtype.fields if f.required or f.requires_human_validation] if dtype else []
    needs_validation = bool(dtype and (dtype.requires_validation or must))
    if needs_validation and must:
        rows = {v.definition_id: v for v in db.scalars(
            select(DocumentMetadataValue).where(DocumentMetadataValue.document_id == doc.id))}
        if all((r := rows.get(f.id)) is not None and r.validation_status == StepStatus.completed for f in must):
            needs_validation = False  # already confirmed by a human (re-analysis)
    if needs_validation:
        doc.status = DocumentStatus.pending_validation
        doc.validation_status = StepStatus.pending
    else:
        doc.status = DocumentStatus.published
        doc.validation_status = StepStatus.skipped
    return {"status": doc.status.value}


STEP_FUNCS: dict[str, Callable[[Session, Document, Path], dict]] = {
    "antivirus": step_antivirus,
    "text_extraction": step_text_extraction,
    "language": step_language,
    "splitting": step_splitting,
    "classification": step_classification,
    "metadata_extraction": step_metadata_extraction,
    "indexing": step_indexing,
    "publication": step_publication,
}


def run_pipeline(tenant_id: uuid.UUID, document_id: uuid.UUID, *, force: bool = False,
                 only_steps: list[str] | None = None) -> dict[str, str]:
    tenant_id_var.set(str(tenant_id))
    summary: dict[str, str] = {}
    with session_scope(tenant_id=tenant_id) as db:
        doc = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id))
        if doc is None:
            log.warning("pipeline_document_missing", extra={"document_id": str(document_id)})
            return {"error": "document_not_found"}
        if doc.status == DocumentStatus.archived:
            return {"skipped": "archived"}  # e.g. a parent that was split into child documents
        doc.status = DocumentStatus.processing
        for step in STEPS:
            _job(db, doc, step)

    workdir = Path(tempfile.mkdtemp(prefix="documind-pipe-"))
    try:
        with session_scope(tenant_id=tenant_id) as db:
            doc = db.get(Document, document_id)
            assert doc is not None
            path = _materialise(doc, workdir)

        for step in STEPS:
            if only_steps is not None and step not in only_steps:
                continue
            with session_scope(tenant_id=tenant_id) as db:
                doc = db.get(Document, document_id)
                assert doc is not None
                job = _job(db, doc, step)
                if job.status in (StepStatus.completed, StepStatus.skipped, StepStatus.not_configured) and not force:
                    summary[step] = f"{job.status.value} (cached)"
                    continue
                job.status = StepStatus.running
                job.attempts += 1
                job.started_at = datetime.now(UTC)
                job.error = None
                db.flush()
                started = time.perf_counter()
                try:
                    _current_attempt.set(job.attempts)
                    job.result = STEP_FUNCS[step](db, doc, path)
                    job.status = StepStatus.completed
                except StepSkip as skip:
                    job.status = skip.status
                    job.result = {"reason": skip.reason}
                except PipelinePause as pause:
                    job.status = StepStatus.completed
                    job.result = pause.result
                    summary[step] = pause.reason
                    _finish(job, started)
                    children = pause.result.get("children") or []
                    if children:
                        db.commit()
                        from app.workers.celery_app import enqueue_processing

                        for child in children:
                            enqueue_processing(tenant_id, uuid.UUID(child))
                    return summary
                except PipelineHalt as halt:
                    job.status = StepStatus.failed
                    job.error = str(halt)
                    summary[step] = "halted"
                    _finish(job, started)
                    return summary
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    _record_failure(tenant_id, document_id, step, exc, started)
                    summary[step] = "failed"
                    return summary
                _finish(job, started)
                summary[step] = job.status.value
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return summary


def _finish(job: ProcessingJob, started: float) -> None:
    job.finished_at = datetime.now(UTC)
    job.duration_ms = int((time.perf_counter() - started) * 1000)


def _record_failure(tenant_id: uuid.UUID, document_id: uuid.UUID, step: str, exc: Exception, started: float) -> None:
    log.error("pipeline_step_failed", extra={"document_id": str(document_id), "step": step, "error": str(exc)})
    with session_scope(tenant_id=tenant_id) as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        job = _job(db, doc, step)
        job.status = StepStatus.failed
        job.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}"[:8000]
        _finish(job, started)
        doc.status = DocumentStatus.failed
        if step == "text_extraction":
            doc.ocr_status = StepStatus.failed
        elif step == "metadata_extraction":
            doc.ai_status = StepStatus.failed
