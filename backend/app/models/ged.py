"""Core ECM domain: folders, documents, versions, types, metadata, tags, relations."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDelete, TenantScoped, Timestamps, UUIDPk


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    pending_validation = "pending_validation"
    published = "published"
    rejected = "rejected"
    archived = "archived"
    failed = "failed"


class StepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    not_configured = "not_configured"


class MetadataDataType(str, enum.Enum):
    text = "text"
    long_text = "long_text"
    integer = "integer"
    decimal = "decimal"
    currency = "currency"
    date = "date"
    datetime = "datetime"
    boolean = "boolean"
    dropdown = "dropdown"
    multi_select = "multi_select"
    reference = "reference"
    calculated = "calculated"


class Folder(UUIDPk, Timestamps, TenantScoped, SoftDelete, Base):
    __tablename__ = "folders"
    __table_args__ = (
        Index(
            "uq_folders_tenant_parent_name_live",
            "tenant_id",
            text("coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class DocumentType(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "document_types"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    color: Mapped[str | None] = mapped_column(String(20))
    icon: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requires_validation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    classification_hints: Mapped[str | None] = mapped_column(Text)  # used by the AI classifier
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    fields: Mapped[list[MetadataDefinition]] = relationship(
        back_populates="document_type",
        order_by="MetadataDefinition.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MetadataDefinition(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "metadata_definitions"
    __table_args__ = (
        UniqueConstraint("document_type_id", "technical_name"),
        UniqueConstraint("object_type_id", "technical_name"),
        # A field belongs either to a document type or to a business-object type, never both.
        CheckConstraint("(document_type_id IS NULL) <> (object_type_id IS NULL)", name="single_owner"),
    )

    document_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_types.id", ondelete="CASCADE"), nullable=True, index=True
    )
    object_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("object_types.id", ondelete="CASCADE"), nullable=True, index=True
    )
    technical_name: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    data_type: Mapped[MetadataDataType] = mapped_column(
        Enum(MetadataDataType, name="metadata_data_type"), nullable=False
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_value: Mapped[object | None] = mapped_column(JSONB)
    validation_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    allowed_values: Mapped[list | None] = mapped_column(JSONB)
    searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ai_extraction_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extraction_prompt: Mapped[str | None] = mapped_column(Text)
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_human_validation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document_type: Mapped[DocumentType | None] = relationship(back_populates="fields")


class Document(UUIDPk, Timestamps, TenantScoped, SoftDelete, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_tenant_sha256", "tenant_id", "sha256"),
        Index("ix_documents_search", "search_vector", postgresql_using="gin"),
        Index("ix_documents_tenant_folder", "tenant_id", "folder_id"),
    )

    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL")
    )
    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    document_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_types.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    storage_provider: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), nullable=False, default=DocumentStatus.uploaded
    )
    language: Mapped[str | None] = mapped_column(String(10))
    content_text: Mapped[str | None] = mapped_column(Text)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )

    scan_status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status"), nullable=False, default=StepStatus.pending
    )
    ocr_status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status", create_type=False), nullable=False, default=StepStatus.pending
    )
    ai_status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status", create_type=False), nullable=False, default=StepStatus.pending
    )
    classification_status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status", create_type=False), nullable=False, default=StepStatus.pending
    )
    validation_status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status", create_type=False), nullable=False, default=StepStatus.pending
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float)

    checked_out_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(original_file_name, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(left(content_text, 200000), '')), 'C')",
            persisted=True,
        ),
    )

    document_type: Mapped[DocumentType | None] = relationship(lazy="joined")
    tags: Mapped[list[DocumentTag]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class DocumentVersion(UUIDPk, TenantScoped, Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(String(1000))
    change_reason: Mapped[str | None] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class DocumentMetadataValue(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "document_metadata_values"
    __table_args__ = (UniqueConstraint("document_id", "definition_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_definitions.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[object | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # manual | ai | connector
    confidence: Mapped[float | None] = mapped_column(Float)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status", create_type=False), nullable=False, default=StepStatus.pending
    )
    validated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    definition: Mapped[MetadataDefinition] = relationship(lazy="joined")


class DocumentTag(UUIDPk, TenantScoped, Base):
    __tablename__ = "document_tags"
    __table_args__ = (UniqueConstraint("document_id", "tag"), Index("ix_document_tags_tenant_tag", "tenant_id", "tag"))

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(80), nullable=False)


class DocumentRelation(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "document_relations"
    __table_args__ = (UniqueConstraint("source_document_id", "target_document_id", "relation_type"),)

    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)  # parent_of | related | replaces | ...
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class OcrPage(UUIDPk, TenantScoped, Base):
    __tablename__ = "ocr_pages"
    __table_args__ = (UniqueConstraint("document_id", "version_number", "page_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    method: Mapped[str] = mapped_column(String(30), nullable=False)  # text_layer | tesseract | plain_text
    confidence: Mapped[float | None] = mapped_column(Float)
    blocks: Mapped[list | None] = mapped_column(JSONB)  # word boxes when the engine provides them


class ProcessingJob(UUIDPk, Timestamps, TenantScoped, Base):
    """One pipeline execution step; unique per (document, version, step) for idempotency."""

    __tablename__ = "processing_jobs"
    __table_args__ = (UniqueConstraint("document_id", "version_number", "step"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status", create_type=False), nullable=False, default=StepStatus.pending
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
