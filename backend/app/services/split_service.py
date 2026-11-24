"""Document Splitting Engine: detect, review, apply or dismiss a split of a multi-document PDF.

Applying a split:
* builds one PDF per segment from the parent's current version (pypdf, no re-encoding);
* creates child documents linked to the parent (``parent_document_id`` + ``split_into`` relation),
  in the same folder, with the parent's tags and the reviewed title / document type;
* reuses the parent's OCR pages (renumbered) so children are not OCR'd twice, and marks the
  antivirus / OCR / language steps as inherited;
* archives the parent (kept for traceability, never deleted) and queues the children's pipeline.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.ai.splitting import Detection, ai_segments, heuristic_segments, validate_segments
from app.core.errors import Conflict, ValidationFailed
from app.models import (
    Document,
    DocumentChunk,
    DocumentRelation,
    DocumentSplitProposal,
    DocumentStatus,
    DocumentTag,
    DocumentType,
    DocumentVersion,
    OcrPage,
    ProcessingJob,
    SplitStatus,
    StepStatus,
)
from app.repositories.base import get_owned
from app.storage.base import object_key
from app.storage.providers import get_storage

INHERITED_STEPS = ("antivirus", "text_extraction", "language")
MAX_SEGMENTS = 200


def is_splittable(doc: Document) -> bool:
    return doc.mime_type == "application/pdf" and (doc.page_count or 0) > 1


def page_texts(db: Session, doc: Document) -> list[tuple[int, str]]:
    rows = db.execute(select(OcrPage.page_number, OcrPage.text).where(
        OcrPage.document_id == doc.id, OcrPage.version_number == doc.current_version)
        .order_by(OcrPage.page_number)).all()
    return [(n, t or "") for n, t in rows]


def current_proposal(db: Session, doc: Document) -> DocumentSplitProposal | None:
    return db.scalar(select(DocumentSplitProposal).where(
        DocumentSplitProposal.document_id == doc.id, DocumentSplitProposal.tenant_id == doc.tenant_id)
        .order_by(DocumentSplitProposal.created_at.desc()).limit(1))


def detect(db: Session, doc: Document, *, key: str, use_ai: bool = True) -> Detection:
    """Heuristic always; AI on top when a provider is configured and the tenant allows it."""
    from app.core.errors import QuotaExceeded
    from app.services.ai_service import AINotConfigured, active_provider, get_setting

    pages = page_texts(db, doc)
    detection = heuristic_segments(pages)
    ai_allowed = bool(get_setting(db, doc.tenant_id, "splitting.ai_enabled", True))
    if use_ai and ai_allowed and active_provider(db, doc.tenant_id) is not None and len(pages) > 1:
        try:
            detection = ai_segments(db, doc, pages, key=key, heuristic=detection)
        except AINotConfigured:
            detection.details["ai"] = {"status": "not_configured"}
        except QuotaExceeded as exc:
            detection.details["ai"] = {"status": "quota_exceeded", "error": exc.message}
        except Exception as exc:  # noqa: BLE001 - provider down: the heuristic proposal still stands
            detection.details["ai"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]}
    elif not ai_allowed:
        detection.details["ai"] = {"status": "disabled"}
    else:
        detection.details["ai"] = {"status": "not_configured"}
    _attach_type_ids(db, doc.tenant_id, detection.segments)
    return detection


def _attach_type_ids(db: Session, tenant_id: uuid.UUID, segments: list[dict[str, Any]]) -> None:
    codes = {t.code: t for t in db.scalars(select(DocumentType).where(DocumentType.tenant_id == tenant_id))}
    for seg in segments:
        code = seg.get("document_type_code")
        seg["document_type_id"] = str(codes[code].id) if code in codes else seg.get("document_type_id")


def save_proposal(db: Session, doc: Document, detection: Detection) -> DocumentSplitProposal:
    db.execute(update(DocumentSplitProposal).where(
        DocumentSplitProposal.document_id == doc.id, DocumentSplitProposal.status == SplitStatus.proposed)
        .values(status=SplitStatus.superseded))
    proposal = DocumentSplitProposal(
        tenant_id=doc.tenant_id, document_id=doc.id, version_number=doc.current_version, method=detection.method,
        page_count=doc.page_count or 0, segments=detection.segments, separator_pages=detection.separator_pages,
        confidence=detection.confidence, details=detection.details,
        status=SplitStatus.proposed if detection.is_multi else SplitStatus.dismissed)
    db.add(proposal)
    db.flush()
    return proposal


def _check_segments(db: Session, doc: Document, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(segments) > MAX_SEGMENTS:
        raise ValidationFailed(f"At most {MAX_SEGMENTS} segments")
    try:
        segs = validate_segments(segments, doc.page_count or 0)
    except ValueError as exc:
        raise ValidationFailed(str(exc), code="invalid_segments") from exc
    if len(segs) == 1 and segs[0]["start_page"] == 1 and segs[0]["end_page"] == doc.page_count:
        raise ValidationFailed("A single segment covering every page is not a split", code="invalid_segments")
    for seg in segs:
        if seg.get("document_type_id"):
            get_owned(db, DocumentType, doc.tenant_id, uuid.UUID(str(seg["document_type_id"])),
                      label="Document type")
    return segs


def apply_split(db: Session, doc: Document, *, user_id: uuid.UUID | None,
                segments: list[dict[str, Any]], proposal: DocumentSplitProposal | None = None) -> list[Document]:
    if not is_splittable(doc):
        raise ValidationFailed("Only PDF documents with more than one page can be split", code="not_splittable")
    if doc.checked_out_by and doc.checked_out_by != user_id:
        raise Conflict("Document is checked out by another user", code="checked_out")
    if db.scalar(select(DocumentSplitProposal.id).where(DocumentSplitProposal.document_id == doc.id,
                                                        DocumentSplitProposal.status == SplitStatus.applied)):
        raise Conflict("This document has already been split", code="already_split")
    segs = _check_segments(db, doc, segments)

    storage = get_storage(doc.storage_provider)
    workdir = Path(tempfile.mkdtemp(prefix="documind-split-"))
    try:
        src = workdir / "parent.pdf"
        with storage.open(doc.storage_path) as fh, open(src, "wb") as out:
            shutil.copyfileobj(fh, out)
        reader = PdfReader(str(src))
        if len(reader.pages) != doc.page_count:
            raise Conflict("The stored file does not match the analysed page count; reprocess first",
                           code="page_count_mismatch")
        ocr = {p.page_number: p for p in db.scalars(select(OcrPage).where(
            OcrPage.document_id == doc.id, OcrPage.version_number == doc.current_version))}
        parent_jobs = {j.step: j for j in db.scalars(select(ProcessingJob).where(
            ProcessingJob.document_id == doc.id, ProcessingJob.version_number == doc.current_version))}
        children: list[Document] = []
        width = len(str(len(segs)))
        for index, seg in enumerate(segs, start=1):
            writer = PdfWriter()
            for n in range(seg["start_page"], seg["end_page"] + 1):
                writer.add_page(reader.pages[n - 1])
            buf = io.BytesIO()
            writer.write(buf)
            data = buf.getvalue()
            sha = hashlib.sha256(data).hexdigest()
            child_id = uuid.uuid4()
            key = object_key(doc.tenant_id, child_id, 1, sha, "pdf")
            get_storage().put(key, io.BytesIO(data), content_type="application/pdf")
            pages_label = (f"p. {seg['start_page']}" if seg["start_page"] == seg["end_page"]
                           else f"p. {seg['start_page']}-{seg['end_page']}")
            title = (str(seg.get("title") or "").strip()
                     or f"{doc.title} — partie {index:0{width}d} ({pages_label})")[:500]
            base_name = Path(doc.file_name).stem[:200]
            file_name = f"{base_name}_part{index:0{width}d}.pdf"
            type_id = uuid.UUID(str(seg["document_type_id"])) if seg.get("document_type_id") else None
            texts = [ocr[n].text for n in range(seg["start_page"], seg["end_page"] + 1) if n in ocr]
            content = "\n\n".join(t for t in texts if t) or None
            child = Document(
                id=child_id, tenant_id=doc.tenant_id, folder_id=doc.folder_id, parent_document_id=doc.id,
                document_type_id=type_id, title=title, file_name=file_name, original_file_name=file_name,
                mime_type="application/pdf", extension="pdf", file_size=len(data), sha256=sha,
                page_count=seg["end_page"] - seg["start_page"] + 1, storage_provider=get_storage().name,
                storage_path=key, current_version=1, owner_id=user_id or doc.owner_id,
                status=DocumentStatus.uploaded, language=doc.language, content_text=content,
                scan_status=doc.scan_status, ocr_status=doc.ocr_status if ocr else StepStatus.pending,
                classification_status=StepStatus.completed if type_id else StepStatus.pending,
            )
            for t in doc.tags:
                child.tags.append(DocumentTag(tenant_id=doc.tenant_id, tag=t.tag))
            db.add(child)
            db.add(DocumentVersion(
                tenant_id=doc.tenant_id, document_id=child_id, version_number=1, author_id=user_id,
                comment=f"Découpé depuis « {doc.title} » ({pages_label})", change_reason="split",
                file_name=file_name, mime_type="application/pdf", file_size=len(data), sha256=sha, storage_path=key))
            db.flush()
            for new_number, n in enumerate(range(seg["start_page"], seg["end_page"] + 1), start=1):
                page = ocr.get(n)
                if page is not None:
                    db.add(OcrPage(tenant_id=doc.tenant_id, document_id=child_id, version_number=1,
                                   page_number=new_number, text=page.text, method=page.method,
                                   confidence=page.confidence, blocks=page.blocks))
            if ocr:
                for step in INHERITED_STEPS:
                    pj = parent_jobs.get(step)
                    status = pj.status if pj is not None and pj.status in (
                        StepStatus.completed, StepStatus.skipped, StepStatus.not_configured) else None
                    if status is None:
                        continue
                    db.add(ProcessingJob(tenant_id=doc.tenant_id, document_id=child_id, version_number=1, step=step,
                                         status=status, attempts=0,
                                         result={"inherited_from": str(doc.id), "pages": [seg["start_page"],
                                                                                           seg["end_page"]]}))
            db.add(ProcessingJob(tenant_id=doc.tenant_id, document_id=child_id, version_number=1, step="splitting",
                                 status=StepStatus.skipped, attempts=0,
                                 result={"reason": "Child of a split document"}))
            db.add(DocumentRelation(tenant_id=doc.tenant_id, source_document_id=doc.id,
                                    target_document_id=child_id, relation_type="split_into", created_by=user_id))
            if type_id:
                from app.services.document_service import _apply_defaults

                db.flush()
                db.refresh(child, ["document_type"])
                _apply_defaults(db, child)
            children.append(child)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    now = datetime.now(UTC)
    if proposal is None or proposal.status != SplitStatus.proposed:
        db.execute(update(DocumentSplitProposal).where(
            DocumentSplitProposal.document_id == doc.id, DocumentSplitProposal.status == SplitStatus.proposed)
            .values(status=SplitStatus.superseded))
        proposal = DocumentSplitProposal(tenant_id=doc.tenant_id, document_id=doc.id,
                                         version_number=doc.current_version, method="manual",
                                         page_count=doc.page_count or 0, segments=segs, separator_pages=[],
                                         details={}, child_document_ids=[])
        db.add(proposal)
    proposal.segments = segs
    proposal.status = SplitStatus.applied
    proposal.decided_by = user_id
    proposal.decided_at = now
    proposal.child_document_ids = [str(c.id) for c in children]
    doc.status = DocumentStatus.archived
    doc.archived_at = now
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))  # children carry the content
    doc.validation_status = StepStatus.completed
    for job in parent_jobs.values():
        if job.status in (StepStatus.pending, StepStatus.running):
            job.status = StepStatus.skipped
            job.result = {"reason": f"Split into {len(children)} documents"}
    db.flush()
    return children


def dismiss(db: Session, doc: Document, *, user_id: uuid.UUID | None) -> DocumentSplitProposal | None:
    proposal = db.scalar(select(DocumentSplitProposal).where(
        DocumentSplitProposal.document_id == doc.id, DocumentSplitProposal.status == SplitStatus.proposed))
    if proposal is None:
        return None
    proposal.status = SplitStatus.dismissed
    proposal.decided_by = user_id
    proposal.decided_at = datetime.now(UTC)
    if doc.status == DocumentStatus.pending_validation:
        doc.status = DocumentStatus.processing
    db.flush()
    return proposal


def proposal_out(p: DocumentSplitProposal | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"id": str(p.id), "status": p.status.value, "method": p.method, "version_number": p.version_number,
            "page_count": p.page_count, "segments": p.segments, "separator_pages": p.separator_pages,
            "confidence": p.confidence, "details": p.details, "decided_at": p.decided_at,
            "child_document_ids": p.child_document_ids, "created_at": p.created_at}
