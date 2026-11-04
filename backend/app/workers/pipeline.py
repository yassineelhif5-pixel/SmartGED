"""Document intelligence pipeline.

Steps are idempotent and individually tracked in ``processing_jobs`` (unique
per document / version / step). Re-running the pipeline skips completed steps
unless ``force=True``. Each step runs in its own transaction so progress is
visible to the UI in real time and a failure never loses earlier work.

Steps (Phase 1-2 scope):
  antivirus → text_extraction (text layer + Tesseract OCR) → language →
  classification → metadata_extraction → indexing → publication

Classification / extraction need an AI provider (Phase 3). Until one is
configured these steps are recorded as ``not_configured`` — never faked.
"""

from __future__ import annotations

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

STEPS = ["antivirus", "text_extraction", "language", "classification", "metadata_extraction", "indexing", "publication"]


class StepSkip(Exception):
    def __init__(self, status: StepStatus, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class PipelineHalt(Exception):
    """Stop the pipeline (e.g. infected file); not a technical failure."""


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


def step_classification(db: Session, doc: Document, path: Path) -> dict:
    if doc.document_type_id:
        doc.classification_status = StepStatus.completed
        raise StepSkip(StepStatus.skipped, "Document type set by the user")
    from app.ai.registry import get_active_provider  # Phase 3 module

    if get_active_provider(db, doc.tenant_id) is None:
        doc.classification_status = StepStatus.not_configured
        raise StepSkip(StepStatus.not_configured, "No AI provider configured for this tenant")
    raise StepSkip(StepStatus.not_configured, "AI classification is delivered in Phase 3")


def step_metadata_extraction(db: Session, doc: Document, path: Path) -> dict:
    from app.ai.registry import get_active_provider

    if get_active_provider(db, doc.tenant_id) is None:
        doc.ai_status = StepStatus.not_configured
        raise StepSkip(StepStatus.not_configured, "No AI provider configured for this tenant")
    raise StepSkip(StepStatus.not_configured, "AI extraction is delivered in Phase 3")


def step_indexing(db: Session, doc: Document, path: Path) -> dict:
    # Full-text index is a generated tsvector column → always consistent with content_text.
    return {"full_text": True, "vector": "phase_4"}


def step_publication(db: Session, doc: Document, path: Path) -> dict:
    needs_validation = bool(doc.document_type and (
        doc.document_type.requires_validation
        or any(f.required or f.requires_human_validation for f in doc.document_type.fields)))
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
    "classification": step_classification,
    "metadata_extraction": step_metadata_extraction,
    "indexing": step_indexing,
    "publication": step_publication,
}


def run_pipeline(tenant_id: uuid.UUID, document_id: uuid.UUID, *, force: bool = False) -> dict[str, str]:
    tenant_id_var.set(str(tenant_id))
    summary: dict[str, str] = {}
    with session_scope(tenant_id=tenant_id) as db:
        doc = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id))
        if doc is None:
            log.warning("pipeline_document_missing", extra={"document_id": str(document_id)})
            return {"error": "document_not_found"}
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
                    job.result = STEP_FUNCS[step](db, doc, path)
                    job.status = StepStatus.completed
                except StepSkip as skip:
                    job.status = skip.status
                    job.result = {"reason": skip.reason}
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
