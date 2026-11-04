"""Document API: upload, explore, view, version, validate, trash."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.core.logging import get_logger
from app.database.session import get_db
from app.models import Document, DocumentStatus, OcrPage, ProcessingJob, StepStatus
from app.repositories.base import get_owned
from app.schemas.common import Message, Page
from app.schemas.ged import (
    CopyRequest,
    DocumentDetail,
    DocumentOut,
    DocumentUpdate,
    JobOut,
    MetadataPatch,
    OcrPageOut,
    RelationIn,
    RelationOut,
    VersionOut,
)
from app.security.context import Principal, require
from app.services import document_service
from app.storage.providers import get_storage
from app.workers.celery_app import enqueue_processing

router = APIRouter(prefix="/documents", tags=["Documents"])
log = get_logger(__name__)


def _detail(db: Session, doc: Document) -> DocumentDetail:
    names = document_service.user_names(db, [doc.owner_id, doc.checked_out_by])
    base = DocumentOut.model_validate(doc).model_dump()
    return DocumentDetail(**base, metadata=document_service.metadata_view(db, doc),
                          owner_name=names.get(doc.owner_id) if doc.owner_id else None,
                          checked_out_by_name=names.get(doc.checked_out_by) if doc.checked_out_by else None)


def _parse_csv(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v.strip()]


@router.get("", response_model=Page[DocumentOut])
def list_documents(
    p: Principal = Depends(require("document:read")), db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=300), folder_id: uuid.UUID | None = None,
    recursive: bool = False, document_type_id: uuid.UUID | None = None, status: DocumentStatus | None = None,
    tag: str | None = None, owner_id: uuid.UUID | None = None, created_from: datetime | None = None,
    created_to: datetime | None = None, trashed: bool = False,
    meta: list[str] = Query(default=[], description="Metadata filters as technical_name:value"),
    sort: Literal["created_at", "updated_at", "title", "file_size", "status", "relevance"] = "created_at",
    order: Literal["asc", "desc"] = "desc", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
) -> Page[DocumentOut]:
    metadata_filters = dict(m.split(":", 1) for m in meta if ":" in m)
    items, total = document_service.search_documents(
        db, p.tenant_id, page, page_size, q=q, folder_id=folder_id, recursive=recursive,
        document_type_id=document_type_id, status=status, tag=tag, owner_id=owner_id, created_from=created_from,
        created_to=created_to, trashed=trashed, sort=sort, order=order, metadata_filters=metadata_filters,
    )
    return Page(items=[DocumentOut.model_validate(d) for d in items], total=total, page=page, page_size=page_size)


@router.post("", response_model=DocumentDetail, status_code=201)
def upload(
    file: UploadFile = File(...), folder_id: uuid.UUID | None = Form(default=None),
    document_type_id: uuid.UUID | None = Form(default=None), title: str | None = Form(default=None, max_length=500),
    tags: str | None = Form(default=None), p: Principal = Depends(require("document:create")),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    outcome = document_service.upload_document(
        db, tenant_id=p.tenant_id, user_id=p.user.id, stream=file.file, filename=file.filename or "document",
        folder_id=folder_id, document_type_id=document_type_id, title=title, tags=_parse_csv(tags),
    )
    doc = outcome.document
    p.audit(db, "document.uploaded", resource_type="document", resource_id=doc.id,
            details={"file": doc.original_file_name, "size": doc.file_size, "sha256": doc.sha256,
                     "duplicate_of": str(outcome.duplicate_of.id) if outcome.duplicate_of else None})
    db.commit()  # the worker must see the committed row
    enqueue_processing(p.tenant_id, doc.id)
    db.refresh(doc)
    return _detail(db, doc)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, p: Principal = Depends(require("document:read")),
                 db: Session = Depends(get_db)) -> DocumentDetail:
    doc = get_owned(db, Document, p.tenant_id, document_id, include_deleted=True, label="Document")
    p.audit(db, "document.viewed", resource_type="document", resource_id=doc.id)
    return _detail(db, doc)


@router.patch("/{document_id}", response_model=DocumentDetail)
def update_document(document_id: uuid.UUID, body: DocumentUpdate, p: Principal = Depends(require("document:update")),
                    db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.update_document(db, p.tenant_id, document_id, **body.model_dump())
    p.audit(db, "document.updated", resource_type="document", resource_id=doc.id,
            details=body.model_dump(exclude_none=True, mode="json"))
    return _detail(db, doc)


@router.put("/{document_id}/metadata", response_model=DocumentDetail)
def update_metadata(document_id: uuid.UUID, body: MetadataPatch, p: Principal = Depends(require("metadata:update")),
                    db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.set_metadata(db, p.tenant_id, document_id, p.user.id, body.values, body.validate_fields,
                                        can_validate=p.can("metadata:validate"))
    p.audit(db, "document.metadata_updated", resource_type="document", resource_id=doc.id,
            details={"fields": sorted(body.values), "validated": body.validate_fields})
    return _detail(db, doc)


@router.post("/{document_id}/reject", response_model=DocumentDetail)
def reject(document_id: uuid.UUID, p: Principal = Depends(require("document:validate")),
           db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.reject_document(db, p.tenant_id, document_id)
    p.audit(db, "document.rejected", resource_type="document", resource_id=doc.id)
    return _detail(db, doc)


@router.get("/{document_id}/download")
def download(document_id: uuid.UUID, version: int | None = None, inline: bool = False,
             p: Principal = Depends(require("document:download")), db: Session = Depends(get_db)) -> StreamingResponse:
    doc = get_owned(db, Document, p.tenant_id, document_id, include_deleted=True, label="Document")
    if doc.scan_status == StepStatus.failed:
        raise Forbidden("This file was quarantined by the antivirus", code="quarantined")
    v = document_service.get_version(db, p.tenant_id, doc.id, version or doc.current_version)
    p.audit(db, "document.downloaded" if not inline else "document.previewed", resource_type="document",
            resource_id=doc.id, details={"version": v.version_number})
    db.commit()
    storage = get_storage(doc.storage_provider)
    disposition = "inline" if inline else "attachment"
    return StreamingResponse(
        storage.iter_chunks(v.storage_path), media_type=v.mime_type,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(v.file_name)}",
                 "Content-Length": str(v.file_size), "X-Content-Type-Options": "nosniff",
                 "Cache-Control": "private, no-store"},
    )


@router.get("/{document_id}/versions", response_model=list[VersionOut])
def versions(document_id: uuid.UUID, p: Principal = Depends(require("document:read")),
             db: Session = Depends(get_db)) -> list:
    from app.models import DocumentVersion

    get_owned(db, Document, p.tenant_id, document_id, include_deleted=True, label="Document")
    return list(db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id,
                                                         DocumentVersion.tenant_id == p.tenant_id)
                           .order_by(DocumentVersion.version_number.desc())))


@router.post("/{document_id}/versions", response_model=DocumentDetail, status_code=201)
def new_version(document_id: uuid.UUID, file: UploadFile = File(...), comment: str | None = Form(default=None),
                change_reason: str | None = Form(default=None), p: Principal = Depends(require("document:update")),
                db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.add_version(db, tenant_id=p.tenant_id, user_id=p.user.id, document_id=document_id,
                                       stream=file.file, filename=file.filename or "document", comment=comment,
                                       change_reason=change_reason)
    p.audit(db, "document.version_added", resource_type="document", resource_id=doc.id,
            details={"version": doc.current_version, "comment": comment})
    db.commit()
    enqueue_processing(p.tenant_id, doc.id)
    db.refresh(doc)
    return _detail(db, doc)


@router.get("/{document_id}/pages", response_model=list[OcrPageOut])
def pages(document_id: uuid.UUID, p: Principal = Depends(require("document:read")),
          db: Session = Depends(get_db)) -> list:
    doc = get_owned(db, Document, p.tenant_id, document_id, include_deleted=True, label="Document")
    return list(db.scalars(select(OcrPage).where(OcrPage.document_id == doc.id, OcrPage.tenant_id == p.tenant_id,
                                                 OcrPage.version_number == doc.current_version)
                           .order_by(OcrPage.page_number)))


@router.get("/{document_id}/jobs", response_model=list[JobOut])
def jobs(document_id: uuid.UUID, p: Principal = Depends(require("document:read")),
         db: Session = Depends(get_db)) -> list:
    doc = get_owned(db, Document, p.tenant_id, document_id, include_deleted=True, label="Document")
    from app.workers.pipeline import STEPS

    rows = db.scalars(select(ProcessingJob).where(ProcessingJob.document_id == doc.id,
                                                  ProcessingJob.version_number == doc.current_version)).all()
    return sorted(rows, key=lambda j: STEPS.index(j.step) if j.step in STEPS else 99)


@router.post("/{document_id}/reprocess", response_model=Message)
def reprocess(document_id: uuid.UUID, p: Principal = Depends(require("processing:administer")),
              db: Session = Depends(get_db)) -> Message:
    doc = get_owned(db, Document, p.tenant_id, document_id, label="Document")
    p.audit(db, "document.reprocess_requested", resource_type="document", resource_id=doc.id)
    db.commit()
    enqueue_processing(p.tenant_id, doc.id, force=True, priority=True)
    return Message(message="Processing re-queued")


@router.post("/{document_id}/checkout", response_model=DocumentDetail)
def checkout(document_id: uuid.UUID, p: Principal = Depends(require("document:update")),
             db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.checkout(db, p.tenant_id, document_id, p.user.id)
    p.audit(db, "document.checked_out", resource_type="document", resource_id=doc.id)
    return _detail(db, doc)


@router.post("/{document_id}/checkin", response_model=DocumentDetail)
def checkin(document_id: uuid.UUID, force: bool = False, p: Principal = Depends(require("document:update")),
            db: Session = Depends(get_db)) -> DocumentDetail:
    if force and not p.can("tenant_settings:administer"):
        raise Forbidden("Force check-in requires administrator rights")
    doc = document_service.checkin(db, p.tenant_id, document_id, p.user.id, force=force)
    p.audit(db, "document.checked_in", resource_type="document", resource_id=doc.id, details={"force": force})
    return _detail(db, doc)


@router.post("/{document_id}/copy", response_model=DocumentDetail, status_code=201)
def copy(document_id: uuid.UUID, body: CopyRequest, p: Principal = Depends(require("document:create", "document:read")),
         db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.copy_document(db, p.tenant_id, document_id, p.user.id, body.folder_id)
    p.audit(db, "document.copied", resource_type="document", resource_id=doc.id, details={"source": str(document_id)})
    return _detail(db, doc)


@router.delete("/{document_id}", response_model=Message)
def trash(document_id: uuid.UUID, p: Principal = Depends(require("document:delete")),
          db: Session = Depends(get_db)) -> Message:
    document_service.trash(db, p.tenant_id, document_id, p.user.id)
    p.audit(db, "document.trashed", resource_type="document", resource_id=document_id)
    return Message(message="Document moved to the trash")


@router.post("/{document_id}/restore", response_model=DocumentDetail)
def restore(document_id: uuid.UUID, p: Principal = Depends(require("document:delete")),
            db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.restore(db, p.tenant_id, document_id)
    p.audit(db, "document.restored", resource_type="document", resource_id=doc.id)
    return _detail(db, doc)


@router.delete("/{document_id}/purge", response_model=Message)
def purge(document_id: uuid.UUID, p: Principal = Depends(require("document:delete", "tenant_settings:administer")),
          db: Session = Depends(get_db)) -> Message:
    doc = get_owned(db, Document, p.tenant_id, document_id, include_deleted=True, label="Document")
    provider = doc.storage_provider
    keys = document_service.purge(db, p.tenant_id, document_id)
    p.audit(db, "document.purged", resource_type="document", resource_id=document_id, details={"objects": len(keys)})
    db.commit()
    storage = get_storage(provider)
    for key in keys:
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001 — orphan objects are reconciled by a maintenance job
            log.warning("purge_object_delete_failed", extra={"key": key})
    return Message(message="Document permanently deleted")


@router.get("/{document_id}/relations", response_model=list[RelationOut])
def relations(document_id: uuid.UUID, p: Principal = Depends(require("document:read")),
              db: Session = Depends(get_db)) -> list[RelationOut]:
    return [RelationOut(id=r.id, relation_type=r.relation_type, direction=d, document=DocumentOut.model_validate(o))
            for r, d, o in document_service.list_relations(db, p.tenant_id, document_id)]


@router.post("/{document_id}/relations", response_model=Message, status_code=201)
def add_relation(document_id: uuid.UUID, body: RelationIn, p: Principal = Depends(require("document:update")),
                 db: Session = Depends(get_db)) -> Message:
    rel = document_service.add_relation(db, p.tenant_id, document_id, body.target_document_id, body.relation_type,
                                        p.user.id)
    p.audit(db, "document.relation_added", resource_type="document", resource_id=document_id,
            details={"target": str(body.target_document_id), "type": body.relation_type, "relation_id": str(rel.id)})
    return Message(message="Relation created")
