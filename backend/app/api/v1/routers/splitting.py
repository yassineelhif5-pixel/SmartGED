"""Document Splitting Engine API: review, apply or dismiss the split of a multi-document PDF."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.database.session import get_db
from app.models import Document, DocumentStatus
from app.repositories.base import get_owned
from app.schemas.ged import DocumentOut
from app.security.context import Principal, require
from app.services import split_service
from app.storage.providers import get_storage
from app.workers.celery_app import enqueue_processing

router = APIRouter(prefix="/documents", tags=["Document splitting"])


class SegmentIn(BaseModel):
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=500)
    document_type_id: uuid.UUID | None = None


class ApplySplit(BaseModel):
    segments: list[SegmentIn] = Field(min_length=1, max_length=split_service.MAX_SEGMENTS)
    proposal_id: uuid.UUID | None = None


class SplitPage(BaseModel):
    page_number: int
    excerpt: str
    chars: int


class SplitState(BaseModel):
    document_id: uuid.UUID
    splittable: bool
    page_count: int | None
    status: DocumentStatus
    parent_document_id: uuid.UUID | None
    proposal: dict[str, Any] | None
    pages: list[SplitPage]


class SplitResult(BaseModel):
    proposal: dict[str, Any] | None
    children: list[DocumentOut]


def _state(db: Session, doc: Document) -> SplitState:
    pages = [SplitPage(page_number=n, excerpt=" ".join(t.split())[:280], chars=len(t.strip()))
             for n, t in split_service.page_texts(db, doc)]
    return SplitState(document_id=doc.id, splittable=split_service.is_splittable(doc), page_count=doc.page_count,
                      status=doc.status, parent_document_id=doc.parent_document_id,
                      proposal=split_service.proposal_out(split_service.current_proposal(db, doc)), pages=pages)


@router.get("/{document_id}/split", response_model=SplitState)
def get_split(document_id: uuid.UUID, p: Principal = Depends(require("document:read")),
              db: Session = Depends(get_db)) -> SplitState:
    return _state(db, get_owned(db, Document, p.tenant_id, document_id, label="Document"))


@router.post("/{document_id}/split/detect", response_model=SplitState)
def detect_split(document_id: uuid.UUID, use_ai: bool = True, p: Principal = Depends(require("document:update")),
                 db: Session = Depends(get_db)) -> SplitState:
    doc = get_owned(db, Document, p.tenant_id, document_id, label="Document")
    if not split_service.is_splittable(doc):
        raise ValidationFailed("Only PDF documents with more than one page can be split", code="not_splittable")
    if doc.status == DocumentStatus.archived:
        raise ValidationFailed("This document is archived (already split?)", code="archived")
    detection = split_service.detect(db, doc, key=f"split-detect:{doc.id}:{uuid.uuid4()}", use_ai=use_ai)
    proposal = split_service.save_proposal(db, doc, detection)
    p.audit(db, "document.split_detected", resource_type="document", resource_id=doc.id,
            details={"method": detection.method, "segments": len(detection.segments),
                     "proposal_id": str(proposal.id)})
    db.commit()
    return _state(db, doc)


@router.post("/{document_id}/split/apply", response_model=SplitResult, status_code=201)
def apply_split(document_id: uuid.UUID, body: ApplySplit,
                p: Principal = Depends(require("document:create", "document:update")),
                db: Session = Depends(get_db)) -> SplitResult:
    doc = get_owned(db, Document, p.tenant_id, document_id, label="Document")
    proposal = split_service.current_proposal(db, doc)
    if body.proposal_id and (proposal is None or proposal.id != body.proposal_id):
        raise NotFound("Split proposal not found or superseded")
    children = split_service.apply_split(
        db, doc, user_id=p.user.id, segments=[s.model_dump(mode="json") for s in body.segments],
        proposal=proposal if body.proposal_id else None)
    p.audit(db, "document.split_applied", resource_type="document", resource_id=doc.id,
            details={"children": [str(c.id) for c in children],
                     "segments": [[s.start_page, s.end_page] for s in body.segments]})
    db.commit()
    for child in children:
        enqueue_processing(p.tenant_id, child.id)
    refreshed = []
    for child in children:
        db.refresh(child)
        refreshed.append(DocumentOut.model_validate(child))
    return SplitResult(proposal=split_service.proposal_out(split_service.current_proposal(db, doc)), children=refreshed)


@router.post("/{document_id}/split/dismiss", response_model=SplitState)
def dismiss_split(document_id: uuid.UUID, p: Principal = Depends(require("document:update")),
                  db: Session = Depends(get_db)) -> SplitState:
    doc = get_owned(db, Document, p.tenant_id, document_id, label="Document")
    proposal = split_service.dismiss(db, doc, user_id=p.user.id)
    if proposal is None:
        raise NotFound("No pending split proposal")
    p.audit(db, "document.split_dismissed", resource_type="document", resource_id=doc.id,
            details={"proposal_id": str(proposal.id)})
    db.commit()
    enqueue_processing(p.tenant_id, doc.id)  # resume: classification → extraction → publication
    db.refresh(doc)
    return _state(db, doc)


@router.get("/{document_id}/pages/{page_number}/thumbnail")
def page_thumbnail(document_id: uuid.UUID, page_number: int, width: int = Query(220, ge=80, le=1200),
                   p: Principal = Depends(require("document:read")), db: Session = Depends(get_db)) -> Response:
    doc = get_owned(db, Document, p.tenant_id, document_id, include_deleted=True, label="Document")
    if doc.mime_type != "application/pdf" or not 1 <= page_number <= (doc.page_count or 0):
        raise NotFound("Page not found")
    if shutil.which("pdftoppm") is None:
        raise NotFound("Page rendering is not configured (poppler-utils missing)")
    workdir = Path(tempfile.mkdtemp(prefix="documind-thumb-"))
    try:
        src = workdir / "doc.pdf"
        with get_storage(doc.storage_provider).open(doc.storage_path) as fh, open(src, "wb") as out:
            shutil.copyfileobj(fh, out)
        prefix = workdir / "thumb"
        subprocess.run(["pdftoppm", "-png", "-scale-to-x", str(width), "-scale-to-y", "-1", "-f", str(page_number),
                        "-l", str(page_number), "-singlefile", str(src), str(prefix)],
                       check=True, capture_output=True, timeout=60)
        data = prefix.with_suffix(".png").read_bytes()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
