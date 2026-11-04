"""Document lifecycle: upload, versions, metadata, check-in/out, trash, relations, search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, QuotaExceeded, ValidationFailed
from app.models import (
    Document,
    DocumentMetadataValue,
    DocumentRelation,
    DocumentStatus,
    DocumentTag,
    DocumentType,
    DocumentVersion,
    Folder,
    StepStatus,
    User,
)
from app.repositories.base import get_owned, paginate
from app.services import metadata_service, tenant_service
from app.storage.base import object_key
from app.storage.providers import get_storage
from app.utils.files import inspect_upload

SORTABLE = {
    "created_at": Document.created_at,
    "updated_at": Document.updated_at,
    "title": func.lower(Document.title),
    "file_size": Document.file_size,
    "status": Document.status,
}


@dataclass
class UploadOutcome:
    document: Document
    duplicate_of: Document | None


def _check_storage_quota(db: Session, tenant_id: uuid.UUID, incoming: int) -> None:
    limit = tenant_service.get_quota(db, tenant_id, "storage_bytes")
    if limit is None:
        return
    used = tenant_service.tenant_usage(db, tenant_id)["storage_bytes"]
    if used + incoming > limit:
        raise QuotaExceeded("Storage quota exceeded for this organisation",
                            details={"used": used, "limit": limit, "incoming": incoming})


def _normalise_tags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        tag = t.strip().lower()[:80]
        if tag and tag not in out:
            out.append(tag)
    return out


def upload_document(
    db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, stream: BinaryIO, filename: str,
    folder_id: uuid.UUID | None, document_type_id: uuid.UUID | None, title: str | None, tags: list[str],
) -> UploadOutcome:
    if folder_id:
        get_owned(db, Folder, tenant_id, folder_id, label="Folder")
    if document_type_id:
        get_owned(db, DocumentType, tenant_id, document_type_id, label="Document type")
    inspected = inspect_upload(stream, filename)
    try:
        _check_storage_quota(db, tenant_id, inspected.size)
        duplicate = db.scalar(
            select(Document).where(Document.tenant_id == tenant_id, Document.sha256 == inspected.sha256,
                                   Document.deleted_at.is_(None)).order_by(Document.created_at).limit(1)
        )
        doc_id = uuid.uuid4()
        storage = get_storage()
        key = object_key(tenant_id, doc_id, 1, inspected.sha256, inspected.extension)
        with open(inspected.path, "rb") as fh:
            storage.put(key, fh, content_type=inspected.mime_type)
    finally:
        Path(inspected.path).unlink(missing_ok=True)

    doc = Document(
        id=doc_id, tenant_id=tenant_id, folder_id=folder_id, document_type_id=document_type_id,
        title=(title or Path(inspected.safe_name).stem)[:500], file_name=inspected.safe_name,
        original_file_name=inspected.safe_name, mime_type=inspected.mime_type, extension=inspected.extension,
        file_size=inspected.size, sha256=inspected.sha256, storage_provider=storage.name, storage_path=key,
        current_version=1, owner_id=user_id, status=DocumentStatus.uploaded,
        duplicate_of_id=duplicate.id if duplicate else None,
        classification_status=StepStatus.completed if document_type_id else StepStatus.pending,
    )
    for tag in _normalise_tags(tags):
        doc.tags.append(DocumentTag(tenant_id=tenant_id, tag=tag))
    db.add(doc)
    db.add(DocumentVersion(
        tenant_id=tenant_id, document_id=doc_id, version_number=1, author_id=user_id, comment="Initial upload",
        file_name=inspected.safe_name, mime_type=inspected.mime_type, file_size=inspected.size,
        sha256=inspected.sha256, storage_path=key,
    ))
    db.flush()
    if document_type_id:
        _apply_defaults(db, doc)
    return UploadOutcome(document=doc, duplicate_of=duplicate)


def add_version(
    db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, document_id: uuid.UUID, stream: BinaryIO,
    filename: str, comment: str | None, change_reason: str | None,
) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    if doc.checked_out_by and doc.checked_out_by != user_id:
        raise Conflict("Document is checked out by another user", code="checked_out")
    inspected = inspect_upload(stream, filename)
    try:
        _check_storage_quota(db, tenant_id, inspected.size)
        version = doc.current_version + 1
        key = object_key(tenant_id, doc.id, version, inspected.sha256, inspected.extension)
        with open(inspected.path, "rb") as fh:
            get_storage(doc.storage_provider).put(key, fh, content_type=inspected.mime_type)
    finally:
        Path(inspected.path).unlink(missing_ok=True)
    db.add(DocumentVersion(
        tenant_id=tenant_id, document_id=doc.id, version_number=version, author_id=user_id, comment=comment,
        change_reason=change_reason, file_name=inspected.safe_name, mime_type=inspected.mime_type,
        file_size=inspected.size, sha256=inspected.sha256, storage_path=key,
    ))
    doc.current_version = version
    doc.file_name = inspected.safe_name
    doc.mime_type = inspected.mime_type
    doc.extension = inspected.extension
    doc.file_size = inspected.size
    doc.sha256 = inspected.sha256
    doc.storage_path = key
    doc.status = DocumentStatus.uploaded
    doc.ocr_status = doc.scan_status = doc.ai_status = StepStatus.pending
    doc.content_text = None
    doc.page_count = None
    db.flush()
    return doc


def _apply_defaults(db: Session, doc: Document) -> None:
    if doc.document_type is None and doc.document_type_id:
        db.refresh(doc, ["document_type"])
    if doc.document_type is None:
        return
    existing = {v.definition_id for v in db.scalars(
        select(DocumentMetadataValue).where(DocumentMetadataValue.document_id == doc.id))}
    for field in doc.document_type.fields:
        if field.default_value is not None and field.id not in existing:
            db.add(DocumentMetadataValue(tenant_id=doc.tenant_id, document_id=doc.id, definition_id=field.id,
                                         value=field.default_value, source="default"))
    db.flush()


# ---------------------------------------------------------------- queries
def build_search(
    tenant_id: uuid.UUID, *, q: str | None, folder_id: uuid.UUID | None, recursive_folder_ids: set[uuid.UUID] | None,
    document_type_id: uuid.UUID | None, status: DocumentStatus | None, tag: str | None, owner_id: uuid.UUID | None,
    created_from: datetime | None, created_to: datetime | None, trashed: bool, sort: str, order: str,
    metadata_filters: dict[str, str] | None = None,
) -> Select:
    stmt = select(Document).where(Document.tenant_id == tenant_id)
    stmt = stmt.where(Document.deleted_at.is_not(None) if trashed else Document.deleted_at.is_(None))
    if recursive_folder_ids is not None:
        stmt = stmt.where(Document.folder_id.in_(recursive_folder_ids))
    elif folder_id:
        stmt = stmt.where(Document.folder_id == folder_id)
    if document_type_id:
        stmt = stmt.where(Document.document_type_id == document_type_id)
    if status:
        stmt = stmt.where(Document.status == status)
    if owner_id:
        stmt = stmt.where(Document.owner_id == owner_id)
    if created_from:
        stmt = stmt.where(Document.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Document.created_at <= created_to)
    if tag:
        stmt = stmt.where(Document.id.in_(select(DocumentTag.document_id).where(
            DocumentTag.tenant_id == tenant_id, DocumentTag.tag == tag.lower())))
    for tech_name, expected in (metadata_filters or {}).items():
        from app.models import MetadataDefinition

        sub = (select(DocumentMetadataValue.document_id)
               .join(MetadataDefinition, MetadataDefinition.id == DocumentMetadataValue.definition_id)
               .where(DocumentMetadataValue.tenant_id == tenant_id, MetadataDefinition.technical_name == tech_name,
                      MetadataDefinition.searchable.is_(True),
                      func.lower(DocumentMetadataValue.value.astext).contains(expected.lower())))
        stmt = stmt.where(Document.id.in_(sub))

    rank = None
    if q and q.strip():
        tsq = func.websearch_to_tsquery("simple", q.strip())
        prefix = func.to_tsquery("simple", _prefix_query(q))
        stmt = stmt.where(or_(Document.search_vector.op("@@")(tsq), Document.search_vector.op("@@")(prefix),
                              Document.original_file_name.ilike(f"%{_escape_like(q.strip())}%", escape="\\")))
        rank = func.ts_rank_cd(Document.search_vector, tsq)
    if rank is not None and sort == "relevance":
        return stmt.order_by(rank.desc(), Document.created_at.desc())
    column = SORTABLE.get(sort, Document.created_at)
    return stmt.order_by(column.asc() if order == "asc" else column.desc(), Document.id)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _prefix_query(q: str) -> str:
    import re

    words = re.findall(r"\w+", q.lower())[:8]
    return " & ".join(f"{w}:*" for w in words) or "''"


def search_documents(db: Session, tenant_id: uuid.UUID, page: int, page_size: int, **filters: Any) -> tuple[list[Document], int]:
    folder_id = filters.get("folder_id")
    if folder_id and filters.pop("recursive", False):
        from app.services.folder_service import _descendant_ids

        filters["recursive_folder_ids"] = _descendant_ids(db, tenant_id, folder_id)
    else:
        filters.pop("recursive", None)
        filters["recursive_folder_ids"] = None
    return paginate(db, build_search(tenant_id, **filters), page, page_size)


def metadata_view(db: Session, doc: Document) -> list[dict[str, Any]]:
    values = {v.definition_id: v for v in db.scalars(
        select(DocumentMetadataValue).where(DocumentMetadataValue.document_id == doc.id,
                                            DocumentMetadataValue.tenant_id == doc.tenant_id))}
    out = []
    fields = doc.document_type.fields if doc.document_type else []
    for f in fields:
        if not f.visible:
            continue
        v = values.get(f.id)
        out.append({
            "definition_id": f.id, "technical_name": f.technical_name, "display_name": f.display_name,
            "data_type": f.data_type, "value": v.value if v else None, "source": v.source if v else "none",
            "confidence": v.confidence if v else None, "source_page": v.source_page if v else None,
            "source_text": v.source_text if v else None,
            "validation_status": v.validation_status if v else StepStatus.pending,
            "validated_at": v.validated_at if v else None, "sensitive": f.sensitive, "required": f.required,
        })
    return out


# --------------------------------------------------------------- mutations
def update_document(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, *, title: str | None,
                    folder_id: uuid.UUID | None, move_to_root: bool, document_type_id: uuid.UUID | None,
                    clear_document_type: bool, tags: list[str] | None) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    if title is not None:
        doc.title = title.strip()
    if move_to_root:
        doc.folder_id = None
    elif folder_id is not None:
        get_owned(db, Folder, tenant_id, folder_id, label="Folder")
        doc.folder_id = folder_id
    if clear_document_type:
        doc.document_type_id = None
        doc.classification_status = StepStatus.pending
    elif document_type_id is not None and document_type_id != doc.document_type_id:
        get_owned(db, DocumentType, tenant_id, document_type_id, label="Document type")
        doc.document_type_id = document_type_id
        doc.classification_status = StepStatus.completed
        doc.classification_confidence = None
        db.flush()
        db.refresh(doc, ["document_type"])
        _apply_defaults(db, doc)
    if tags is not None:
        wanted = _normalise_tags(tags)
        doc.tags[:] = [t for t in doc.tags if t.tag in wanted]
        have = {t.tag for t in doc.tags}
        for tag in wanted:
            if tag not in have:
                doc.tags.append(DocumentTag(tenant_id=tenant_id, tag=tag))
    db.flush()
    return doc


def set_metadata(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID,
                 values: dict[str, Any], validate_fields: list[str], can_validate: bool) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    if doc.document_type is None:
        raise ValidationFailed("Assign a document type before editing metadata", code="no_document_type")
    fields = {f.technical_name: f for f in doc.document_type.fields}
    unknown = set(values) - set(fields) | set(validate_fields) - set(fields)
    if unknown:
        raise ValidationFailed("Unknown metadata fields", details={"fields": sorted(unknown)})
    if validate_fields and not can_validate:
        raise Forbidden("Missing permission metadata:validate", code="permission_denied")
    existing = {v.definition_id: v for v in db.scalars(
        select(DocumentMetadataValue).where(DocumentMetadataValue.document_id == doc.id))}
    now = datetime.now(UTC)
    errors = []
    for name, raw in values.items():
        defn = fields[name]
        try:
            value = metadata_service.coerce_value(defn, raw)
        except ValidationFailed as exc:
            errors.append({"field": name, "message": exc.message})
            continue
        row = existing.get(defn.id)
        if row is None:
            row = DocumentMetadataValue(tenant_id=tenant_id, document_id=doc.id, definition_id=defn.id)
            db.add(row)
            existing[defn.id] = row
        if row.value != value:
            row.value = value
            row.source = "manual"
            row.confidence = None
            row.validation_status = StepStatus.pending
            row.validated_by = None
            row.validated_at = None
    if errors:
        raise ValidationFailed("Some metadata values are invalid", details=errors)
    for name in validate_fields:
        defn = fields[name]
        row = existing.get(defn.id)
        if row is None:
            row = DocumentMetadataValue(tenant_id=tenant_id, document_id=doc.id, definition_id=defn.id, value=None)
            db.add(row)
            existing[defn.id] = row
        if defn.required and row.value in (None, "", []):
            raise ValidationFailed(f"{defn.display_name}: a required value cannot be validated empty")
        row.validation_status = StepStatus.completed
        row.validated_by = user_id
        row.validated_at = now
    db.flush()
    _refresh_validation_state(db, doc, existing)
    return doc


def _refresh_validation_state(db: Session, doc: Document, rows: dict[uuid.UUID, DocumentMetadataValue]) -> None:
    """A document is published once every required / sensitive field is validated."""
    if doc.document_type is None or doc.status in (DocumentStatus.processing, DocumentStatus.uploaded,
                                                   DocumentStatus.rejected, DocumentStatus.archived):
        return
    # Fields a human must confirm: required ones and those flagged for human validation
    # (financial / legal data). Optional untouched fields never block publication.
    must = [f for f in doc.document_type.fields if f.required or f.requires_human_validation]
    if not must and doc.document_type.requires_validation:
        must = [f for f in doc.document_type.fields if (r := rows.get(f.id)) is not None and r.value is not None]
    done = all((r := rows.get(f.id)) is not None and r.validation_status == StepStatus.completed for f in must)
    if done:
        doc.validation_status = StepStatus.completed
        doc.status = DocumentStatus.published
    else:
        doc.validation_status = StepStatus.pending
        doc.status = DocumentStatus.pending_validation
    db.flush()


def reject_document(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    doc.status = DocumentStatus.rejected
    doc.validation_status = StepStatus.failed
    db.flush()
    return doc


def checkout(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    if doc.checked_out_by and doc.checked_out_by != user_id:
        raise Conflict("Document already checked out by another user", code="checked_out")
    doc.checked_out_by = user_id
    doc.checked_out_at = datetime.now(UTC)
    db.flush()
    return doc


def checkin(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID, *, force: bool) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    if doc.checked_out_by is None:
        return doc
    if doc.checked_out_by != user_id and not force:
        raise Forbidden("Only the user who checked out the document (or an administrator) can release it")
    doc.checked_out_by = None
    doc.checked_out_at = None
    db.flush()
    return doc


def trash(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, label="Document")
    if doc.checked_out_by and doc.checked_out_by != user_id:
        raise Conflict("Document is checked out by another user", code="checked_out")
    doc.deleted_at = datetime.now(UTC)
    db.flush()
    return doc


def restore(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    doc = get_owned(db, Document, tenant_id, document_id, include_deleted=True, label="Document")
    if doc.deleted_at is None:
        return doc
    if doc.folder_id:
        folder = db.get(Folder, doc.folder_id)
        if folder is None or folder.deleted_at is not None:
            doc.folder_id = None  # original folder is gone → restore at root
    doc.deleted_at = None
    db.flush()
    return doc


def purge(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> list[str]:
    """Permanently delete a trashed document. Returns storage keys to delete after commit."""
    doc = get_owned(db, Document, tenant_id, document_id, include_deleted=True, label="Document")
    if doc.deleted_at is None:
        raise ValidationFailed("Only documents in the trash can be purged", code="not_in_trash")
    keys = list(db.scalars(select(DocumentVersion.storage_path).where(DocumentVersion.document_id == doc.id)))
    db.delete(doc)
    db.flush()
    return keys


def copy_document(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID,
                  folder_id: uuid.UUID | None) -> Document:
    src = get_owned(db, Document, tenant_id, document_id, label="Document")
    if folder_id:
        get_owned(db, Folder, tenant_id, folder_id, label="Folder")
    storage = get_storage(src.storage_provider)
    new_id = uuid.uuid4()
    key = object_key(tenant_id, new_id, 1, src.sha256, src.extension)
    with storage.open(src.storage_path) as fh:
        storage.put(key, fh, content_type=src.mime_type)
    copy = Document(
        id=new_id, tenant_id=tenant_id, folder_id=folder_id if folder_id else src.folder_id,
        document_type_id=src.document_type_id, title=f"{src.title} (copie)", file_name=src.file_name,
        original_file_name=src.original_file_name, mime_type=src.mime_type, extension=src.extension,
        file_size=src.file_size, sha256=src.sha256, page_count=src.page_count, storage_provider=storage.name,
        storage_path=key, current_version=1, owner_id=user_id, status=src.status, language=src.language,
        content_text=src.content_text, duplicate_of_id=src.id, scan_status=src.scan_status,
        ocr_status=src.ocr_status, ai_status=src.ai_status, classification_status=src.classification_status,
        validation_status=src.validation_status, classification_confidence=src.classification_confidence,
    )
    for t in src.tags:
        copy.tags.append(DocumentTag(tenant_id=tenant_id, tag=t.tag))
    db.add(copy)
    db.add(DocumentVersion(tenant_id=tenant_id, document_id=new_id, version_number=1, author_id=user_id,
                           comment=f"Copied from {src.id}", file_name=src.file_name, mime_type=src.mime_type,
                           file_size=src.file_size, sha256=src.sha256, storage_path=key))
    for v in db.scalars(select(DocumentMetadataValue).where(DocumentMetadataValue.document_id == src.id)):
        db.add(DocumentMetadataValue(tenant_id=tenant_id, document_id=new_id, definition_id=v.definition_id,
                                     value=v.value, source=v.source, confidence=v.confidence,
                                     source_page=v.source_page, source_text=v.source_text,
                                     validation_status=v.validation_status))
    db.add(DocumentRelation(tenant_id=tenant_id, source_document_id=src.id, target_document_id=new_id,
                            relation_type="copied_to", created_by=user_id))
    db.flush()
    return copy


def get_version(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID, number: int) -> DocumentVersion:
    get_owned(db, Document, tenant_id, document_id, include_deleted=True, label="Document")
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id,
                                                      DocumentVersion.tenant_id == tenant_id,
                                                      DocumentVersion.version_number == number))
    if version is None:
        raise NotFound("Version not found")
    return version


def add_relation(db: Session, tenant_id: uuid.UUID, source_id: uuid.UUID, target_id: uuid.UUID,
                 relation_type: str, user_id: uuid.UUID) -> DocumentRelation:
    if source_id == target_id:
        raise ValidationFailed("A document cannot be related to itself")
    get_owned(db, Document, tenant_id, source_id, label="Document")
    get_owned(db, Document, tenant_id, target_id, label="Target document")
    exists = db.scalar(select(DocumentRelation).where(and_(
        DocumentRelation.source_document_id == source_id, DocumentRelation.target_document_id == target_id,
        DocumentRelation.relation_type == relation_type)))
    if exists:
        return exists
    rel = DocumentRelation(tenant_id=tenant_id, source_document_id=source_id, target_document_id=target_id,
                           relation_type=relation_type, created_by=user_id)
    db.add(rel)
    db.flush()
    return rel


def list_relations(db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> list[tuple[DocumentRelation, str, Document]]:
    get_owned(db, Document, tenant_id, document_id, label="Document")
    rels = db.scalars(select(DocumentRelation).where(
        DocumentRelation.tenant_id == tenant_id,
        or_(DocumentRelation.source_document_id == document_id, DocumentRelation.target_document_id == document_id),
    )).all()
    out = []
    for r in rels:
        outgoing = r.source_document_id == document_id
        other = db.get(Document, r.target_document_id if outgoing else r.source_document_id)
        if other is not None and other.deleted_at is None:
            out.append((r, "outgoing" if outgoing else "incoming", other))
    return out


def user_names(db: Session, ids: list[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = [i for i in ids if i]
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all())
