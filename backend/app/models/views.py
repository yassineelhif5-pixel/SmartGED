"""Saved document views (filters + sort) and per-user preferences.

* ``scope = tenant``  : configured by an administrator and shared with every member.
* ``scope = personal``: owned and visible by one user only.

Default resolution for a user: personal preference → tenant default view → none.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantScoped, Timestamps, UUIDPk


class ViewScope(str, enum.Enum):
    tenant = "tenant"
    personal = "personal"


class DocumentView(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "document_views"
    __table_args__ = (
        CheckConstraint("(scope = 'personal') = (owner_id IS NOT NULL)", name="owner_matches_scope"),
        # at most one shared default per tenant
        Index("uq_document_views_tenant_default", "tenant_id", unique=True,
              postgresql_where=text("scope = 'tenant' AND is_default")),
        Index("ix_document_views_owner", "tenant_id", "owner_id"),
    )

    scope: Mapped[ViewScope] = mapped_column(Enum(ViewScope, name="view_scope"), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    icon: Mapped[str | None] = mapped_column(String(40))
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class UserPreference(UUIDPk, Timestamps, TenantScoped, Base):
    """User-level override in the Platform → Tenant → User settings hierarchy."""

    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
