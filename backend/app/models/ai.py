"""AI domain: providers (per tenant, encrypted keys), versioned prompts, usage ledger, versioned prices."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TenantScoped, Timestamps, UUIDPk


class ProviderKind(str, enum.Enum):
    openai = "openai"
    azure_openai = "azure_openai"
    anthropic = "anthropic"
    gemini = "gemini"
    openai_compatible = "openai_compatible"  # Ollama, vLLM, LM Studio, Mistral… (local or hosted)


class PromptStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class AIProvider(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "ai_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        Index("uq_ai_providers_tenant_default", "tenant_id", unique=True, postgresql_where=text("is_default")),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[ProviderKind] = mapped_column(Enum(ProviderKind, name="ai_provider_kind"), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    api_version: Mapped[str | None] = mapped_column(String(40))  # Azure OpenAI
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    api_key_hint: Mapped[str | None] = mapped_column(String(12))
    default_model: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(120))  # set → used for semantic search
    temperature: Mapped[float | None] = mapped_column(Float)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL"))
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_message: Mapped[str | None] = mapped_column(String(1000))


class AIPrompt(UUIDPk, Timestamps, Base):
    """A prompt slot identified by ``code``. ``tenant_id`` NULL = platform default, readable by every tenant."""

    __tablename__ = "ai_prompts"
    __table_args__ = (
        Index("uq_ai_prompts_global_code", "code", unique=True, postgresql_where=text("tenant_id IS NULL")),
        Index("uq_ai_prompts_tenant_code", "tenant_id", "code", unique=True,
              postgresql_where=text("tenant_id IS NOT NULL")),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)  # classification | metadata_extraction | …
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    published_version: Mapped[int | None] = mapped_column(Integer)

    versions: Mapped[list[AIPromptVersion]] = relationship(
        back_populates="prompt", order_by="AIPromptVersion.version.desc()", cascade="all, delete-orphan",
        lazy="selectin")


class AIPromptVersion(UUIDPk, Timestamps, Base):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version"),)

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_prompts.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PromptStatus] = mapped_column(Enum(PromptStatus, name="ai_prompt_status"), nullable=False,
                                                 default=PromptStatus.draft)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    output_format: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    model: Mapped[str | None] = mapped_column(String(120))  # optional override of the provider default
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    prompt: Mapped[AIPrompt] = relationship(back_populates="versions")


class AIPromptTest(UUIDPk, TenantScoped, Base):
    __tablename__ = "ai_prompt_tests"

    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_prompt_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                          ForeignKey("documents.id", ondelete="SET NULL"))
    provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                          ForeignKey("ai_providers.id", ondelete="SET NULL"))
    model: Mapped[str | None] = mapped_column(String(120))
    output_text: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict | None] = mapped_column(JSONB)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=text("now()"))


class AIUsageEvent(Base):
    """Consumption ledger. ``idempotency_key`` is unique: a retried task never counts twice."""

    __tablename__ = "ai_usage_events"
    __table_args__ = (Index("ix_ai_usage_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    feature: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provider_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_code: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[int | None] = mapped_column(Integer)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    price_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=text("now()"))


class AIModelPrice(UUIDPk, Timestamps, Base):
    """Platform price list, versioned by ``effective_from``. Prices per million tokens, in USD."""

    __tablename__ = "ai_model_prices"
    __table_args__ = (UniqueConstraint("provider_kind", "model", "effective_from"),)

    provider_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    output_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
