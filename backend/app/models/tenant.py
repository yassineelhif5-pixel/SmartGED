"""SaaS domain: plans, tenants, modules and quotas."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TenantScoped, Timestamps, UUIDPk


class TenantStatus(str, enum.Enum):
    provisioning = "provisioning"
    active = "active"
    suspended = "suspended"
    archived = "archived"


class SubscriptionPlan(UUIDPk, Timestamps, Base):
    __tablename__ = "subscription_plans"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10 * 1024**3)
    monthly_ai_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    modules: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Tenant(UUIDPk, Timestamps, Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"), nullable=False, default=TenantStatus.provisioning
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"))
    storage_provider: Mapped[str] = mapped_column(String(30), nullable=False, default="local")
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[SubscriptionPlan | None] = relationship(lazy="joined")


class TenantSetting(UUIDPk, Timestamps, TenantScoped, Base):
    """Tenant override of a platform default (Platform → Tenant → User hierarchy)."""

    __tablename__ = "tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)


class SystemSetting(UUIDPk, Timestamps, Base):
    """Platform default settings."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))


class TenantModule(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "tenant_modules"
    __table_args__ = (UniqueConstraint("tenant_id", "module"),)

    module: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TenantQuota(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "tenant_quotas"
    __table_args__ = (UniqueConstraint("tenant_id", "metric"),)

    metric: Mapped[str] = mapped_column(String(60), nullable=False)  # users | storage_bytes | ai_credits
    limit_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
