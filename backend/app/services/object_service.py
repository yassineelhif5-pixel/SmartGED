"""Business objects (non-document records) — CRUD, links to documents, metadata autofill.

Autofill convention ("alimenter un document"): for each field of the document type,
the value comes from, in order:
  1. an explicit mapping given by the caller (document field → object attribute),
  2. an object attribute with the same technical name,
  3. ``{object_type_code}_name`` / ``{object_type_code}_code`` ← the object's name / code
     (e.g. ``supplier_name`` is filled from a *supplier* object's name).
Only empty fields are filled unless ``overwrite`` is requested; filled values are marked
``source = "object"`` and still go through normal validation.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import (
    BusinessObject,
    Document,
    DocumentMetadataValue,
    DocumentObjectLink,
    MetadataDataType,
    ObjectStatus,
    ObjectType,
    StepStatus,
)
from app.repositories.base import get_owned, paginate
from app.services import metadata_service


def coerce_attributes(obj_type: ObjectType, raw: dict[str, Any]) -> dict[str, Any]:
    fields = {f.technical_name: f for f in obj_type.fields}
    unknown = set(raw) - set(fields)
    if unknown:
        raise ValidationFailed("Unknown attributes", details={"fields": sorted(unknown)})
    out: dict[str, Any] = {}
    errors = []
    for name, defn in fields.items():
        if defn.data_type == MetadataDataType.calculated:
            continue
        try:
            value = metadata_service.coerce_value(defn, raw.get(name, defn.default_value))
        except ValidationFailed as exc:
            errors.append({"field": name, "message": exc.message})
            continue
        if value is not None:
            out[name] = value
    if errors:
        raise ValidationFailed("Some attributes are invalid", details=errors)
    return out


def object_type_by_code(db: Session, tenant_id: uuid.UUID, code: str) -> ObjectType | None:
    return db.scalar(select(ObjectType).where(ObjectType.tenant_id == tenant_id, ObjectType.code == code))


def search_objects(db: Session, tenant_id: uuid.UUID, *, object_type_id: uuid.UUID | None, q: str | None,
                   status: ObjectStatus | None, page: int, page_size: int) -> tuple[list[BusinessObject], int]:
    stmt = select(BusinessObject).where(BusinessObject.tenant_id == tenant_id)
    if object_type_id:
        stmt = stmt.where(BusinessObject.object_type_id == object_type_id)
    if status:
        stmt = stmt.where(BusinessObject.status == status)
    if q and q.strip():
        term = q.strip()
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(
            BusinessObject.search_vector.op("@@")(func.websearch_to_tsquery("simple", term)),
            BusinessObject.name.ilike(like, escape="\\"), BusinessObject.code.ilike(like, escape="\\"),
        ))
    return paginate(db, stmt.order_by(func.lower(BusinessObject.name)), page, page_size)


def document_counts(db: Session, object_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not object_ids:
        return {}
    rows = db.execute(
        select(DocumentObjectLink.object_id, func.count(func.distinct(DocumentObjectLink.document_id)))
        .join(Document, Document.id == DocumentObjectLink.document_id)
        .where(DocumentObjectLink.object_id.in_(object_ids), Document.deleted_at.is_(None))
        .group_by(DocumentObjectLink.object_id)
    ).all()
    return {oid: int(c) for oid, c in rows}


def save_object(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, *, object_id: uuid.UUID | None,
                object_type_id: uuid.UUID, code: str, name: str, description: str | None,
                status: ObjectStatus, attributes: dict[str, Any]) -> BusinessObject:
    obj_type = get_owned(db, ObjectType, tenant_id, object_type_id, label="Object type")
    code = code.strip()
    clash = db.scalar(select(BusinessObject.id).where(
        BusinessObject.tenant_id == tenant_id, BusinessObject.object_type_id == object_type_id,
        BusinessObject.code == code, BusinessObject.id != (object_id or uuid.UUID(int=0))))
    if clash:
        raise Conflict(f"An object with reference '{code}' already exists", code="object_code_taken")
    clean = coerce_attributes(obj_type, attributes)
    if object_id:
        obj = get_owned(db, BusinessObject, tenant_id, object_id, label="Object")
        if obj.object_type_id != object_type_id:
            raise ValidationFailed("The type of an object cannot be changed")
    else:
        if not obj_type.is_active:
            raise ValidationFailed("This object type is deactivated")
        obj = BusinessObject(tenant_id=tenant_id, object_type_id=object_type_id, created_by=user_id)
        db.add(obj)
    obj.code, obj.name, obj.description, obj.status, obj.attributes = code, name.strip(), description, status, clean
    db.flush()
    db.refresh(obj, ["object_type"])
    return obj


def delete_object(db: Session, tenant_id: uuid.UUID, object_id: uuid.UUID) -> int:
    """Delete an object. If documents still reference it, archive it instead. Returns linked count."""
    obj = get_owned(db, BusinessObject, tenant_id, object_id, label="Object")
    linked = document_counts(db, [obj.id]).get(obj.id, 0)
    if linked:
        obj.status = ObjectStatus.archived
    else:
        db.delete(obj)
    db.flush()
    return linked


# ------------------------------------------------------------------ links
def link(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, object_id: uuid.UUID, role: str,
         user_id: uuid.UUID) -> DocumentObjectLink:
    get_owned(db, Document, tenant_id, document_id, label="Document")
    obj = get_owned(db, BusinessObject, tenant_id, object_id, label="Object")
    existing = db.scalar(select(DocumentObjectLink).where(
        DocumentObjectLink.document_id == document_id, DocumentObjectLink.object_id == obj.id,
        DocumentObjectLink.role == role))
    if existing:
        return existing
    row = DocumentObjectLink(tenant_id=tenant_id, document_id=document_id, object_id=obj.id, role=role,
                             created_by=user_id)
    db.add(row)
    db.flush()
    return row


def unlink(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, link_id: uuid.UUID) -> None:
    row = db.scalar(select(DocumentObjectLink).where(DocumentObjectLink.id == link_id,
                                                     DocumentObjectLink.document_id == document_id,
                                                     DocumentObjectLink.tenant_id == tenant_id))
    if row is None:
        raise NotFound("Link not found")
    db.delete(row)
    db.flush()


def links_of_document(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> list[DocumentObjectLink]:
    get_owned(db, Document, tenant_id, document_id, include_deleted=True, label="Document")
    return list(db.scalars(select(DocumentObjectLink).where(
        DocumentObjectLink.tenant_id == tenant_id, DocumentObjectLink.document_id == document_id)
        .order_by(DocumentObjectLink.created_at)))


# --------------------------------------------------------------- autofill
def apply_to_document(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, object_id: uuid.UUID,
                      user_id: uuid.UUID, *, overwrite: bool, mapping: dict[str, str] | None = None,
                      only_fields: set[str] | None = None) -> tuple[list[str], list[str]]:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    if doc.document_type is None:
        raise ValidationFailed("Assign a document type before filling its metadata", code="no_document_type")
    obj = get_owned(db, BusinessObject, tenant_id, object_id, label="Object")
    source: dict[str, Any] = dict(obj.attributes or {})
    type_code = obj.object_type.code
    source.update({"name": obj.name, "code": obj.code, f"{type_code}_name": obj.name, f"{type_code}_code": obj.code})
    mapping = mapping or {}
    rows = {v.definition_id: v for v in db.scalars(
        select(DocumentMetadataValue).where(DocumentMetadataValue.document_id == doc.id))}
    filled, skipped = [], []
    for defn in doc.document_type.fields:
        name = defn.technical_name
        if only_fields is not None and name not in only_fields:
            continue
        key = mapping.get(name, name)
        if key not in source or defn.data_type == MetadataDataType.reference:
            continue
        row = rows.get(defn.id)
        if row is not None and row.value not in (None, "", []) and not overwrite:
            skipped.append(name)
            continue
        try:
            value = metadata_service.coerce_value(defn, source[key])
        except ValidationFailed:
            skipped.append(name)
            continue
        if row is None:
            row = DocumentMetadataValue(tenant_id=tenant_id, document_id=doc.id, definition_id=defn.id)
            db.add(row)
        row.value, row.source, row.confidence = value, "object", None
        row.source_text = f"{obj.object_type.name} {obj.code} — {obj.name}"
        row.validation_status, row.validated_by, row.validated_at = StepStatus.pending, None, None
        filled.append(name)
    link(db, tenant_id, doc.id, obj.id, "source", user_id)
    db.flush()
    return filled, skipped


def reference_labels(db: Session, tenant_id: uuid.UUID, ids: list[str]) -> dict[str, str]:
    valid = []
    for i in ids:
        try:
            valid.append(uuid.UUID(str(i)))
        except ValueError:
            continue
    if not valid:
        return {}
    rows = db.execute(select(BusinessObject.id, BusinessObject.code, BusinessObject.name)
                      .where(BusinessObject.tenant_id == tenant_id, BusinessObject.id.in_(valid))).all()
    return {str(i): f"{c} — {n}" for i, c, n in rows}


