"""Business objects: non-document records (supplier, customer, project, asset…).

They are configured like document types (an ``ObjectType`` owns
``MetadataDefinition`` fields), can be linked to documents, referenced by
``reference`` metadata fields and used to fill a document's metadata.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Computed, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TenantScoped, Timestamps, UUIDPk
from app.models.ged import MetadataDefinition


class ObjectStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class ObjectType(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "object_types"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    color: Mapped[str | None] = mapped_column(String(20))
    icon: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[int] = mapped_column(nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    fields: Mapped[list[MetadataDefinition]] = relationship(
        primaryjoin="ObjectType.id == MetadataDefinition.object_type_id",
        foreign_keys="MetadataDefinition.object_type_id",
        order_by="MetadataDefinition.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BusinessObject(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "business_objects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "object_type_id", "code"),
        Index("ix_business_objects_search", "search_vector", postgresql_using="gin"),
    )

    object_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("object_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)  # business reference, e.g. FRN-0042
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ObjectStatus] = mapped_column(Enum(ObjectStatus, name="object_status"), nullable=False,
                                                 default=ObjectStatus.active)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple', coalesce(name, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(code, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(description, '')), 'C')",
            persisted=True,
        ),
    )

    object_type: Mapped[ObjectType] = relationship(lazy="joined")


class DocumentObjectLink(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "document_object_links"
    __table_args__ = (UniqueConstraint("document_id", "object_id", "role"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_objects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(80), nullable=False, default="related")  # e.g. supplier_ref
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    object: Mapped[BusinessObject] = relationship(lazy="joined")
