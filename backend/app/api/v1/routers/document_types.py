"""Document Type Designer & Metadata Designer API.

Every structural change to a type's fields bumps ``schema_version`` so that
extracted values can always be traced back to the schema they were produced with.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.database.session import get_db
from app.models import Document, DocumentType, MetadataDefinition
from app.repositories.base import get_owned
from app.schemas.common import Message
from app.schemas.ged import DocumentTypeIn, DocumentTypeOut
from app.security.context import Principal, require
from app.services import schema_designer

router = APIRouter(prefix="/document-types", tags=["Document types & metadata"])

def _out(db: Session, dt: DocumentType) -> DocumentTypeOut:
    count = db.scalar(select(func.count()).select_from(Document).where(
        Document.document_type_id == dt.id, Document.deleted_at.is_(None))) or 0
    return DocumentTypeOut.model_validate(dt).model_copy(update={"document_count": int(count)})


@router.get("", response_model=list[DocumentTypeOut])
def list_types(p: Principal = Depends(require("document_type:read")), db: Session = Depends(get_db)) -> list:
    return [_out(db, t) for t in db.scalars(select(DocumentType).where(DocumentType.tenant_id == p.tenant_id)
                                            .order_by(DocumentType.name))]


@router.get("/{type_id}", response_model=DocumentTypeOut)
def get_type(type_id: uuid.UUID, p: Principal = Depends(require("document_type:read")),
             db: Session = Depends(get_db)) -> DocumentTypeOut:
    return _out(db, get_owned(db, DocumentType, p.tenant_id, type_id, label="Document type"))


@router.post("", response_model=DocumentTypeOut, status_code=201)
def create_type(body: DocumentTypeIn, p: Principal = Depends(require("document_type:create")),
                db: Session = Depends(get_db)) -> DocumentTypeOut:
    schema_designer.validate_fields(db, p.tenant_id, body.fields)
    if db.scalar(select(DocumentType.id).where(DocumentType.tenant_id == p.tenant_id, DocumentType.code == body.code)):
        raise Conflict("A document type with this code already exists")
    dt = DocumentType(tenant_id=p.tenant_id, **body.model_dump(exclude={"fields"}))
    for pos, f in enumerate(body.fields):
        dt.fields.append(MetadataDefinition(tenant_id=p.tenant_id, position=pos, **f.model_dump(exclude={"id"})))
    db.add(dt)
    db.flush()
    p.audit(db, "document_type.created", resource_type="document_type", resource_id=dt.id,
            details={"code": dt.code, "fields": [f.technical_name for f in body.fields]})
    return _out(db, dt)


@router.put("/{type_id}", response_model=DocumentTypeOut)
def update_type(type_id: uuid.UUID, body: DocumentTypeIn, p: Principal = Depends(require("document_type:update")),
                db: Session = Depends(get_db)) -> DocumentTypeOut:
    schema_designer.validate_fields(db, p.tenant_id, body.fields)
    dt = get_owned(db, DocumentType, p.tenant_id, type_id, label="Document type")
    if body.code != dt.code and db.scalar(select(DocumentType.id).where(
            DocumentType.tenant_id == p.tenant_id, DocumentType.code == body.code)):
        raise Conflict("A document type with this code already exists")
    for key, value in body.model_dump(exclude={"fields"}).items():
        setattr(dt, key, value)

    kept, structural_change = schema_designer.sync_fields(dt.fields, body.fields, tenant_id=p.tenant_id,
                                                          owner={})
    dt.fields[:] = kept
    if structural_change:
        dt.schema_version += 1
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise Conflict("Field definitions conflict (duplicate technical name?)") from exc
    p.audit(db, "document_type.updated", resource_type="document_type", resource_id=dt.id,
            details={"schema_version": dt.schema_version, "fields": [f.technical_name for f in body.fields]})
    return _out(db, dt)


@router.delete("/{type_id}", response_model=Message)
def delete_type(type_id: uuid.UUID, p: Principal = Depends(require("document_type:delete")),
                db: Session = Depends(get_db)) -> Message:
    dt = get_owned(db, DocumentType, p.tenant_id, type_id, label="Document type")
    in_use = db.scalar(select(func.count()).select_from(Document).where(Document.document_type_id == dt.id)) or 0
    if in_use:
        dt.is_active = False
        p.audit(db, "document_type.deactivated", resource_type="document_type", resource_id=dt.id)
        return Message(message=f"Type used by {in_use} document(s): it has been deactivated instead of deleted")
    db.delete(dt)
    p.audit(db, "document_type.deleted", resource_type="document_type", resource_id=type_id)
    return Message(message="Document type deleted")
