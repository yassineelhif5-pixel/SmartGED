from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.models import PromptStatus, ProviderKind
from app.schemas.common import ORM


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: ProviderKind
    base_url: HttpUrl | None = None
    api_version: str | None = Field(default=None, max_length=40)
    api_key: str | None = Field(default=None, max_length=500, description="Write-only. Omit to keep the stored key.")
    clear_api_key: bool = False
    default_model: str = Field(min_length=1, max_length=120)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=64, le=64000)
    timeout_seconds: int = Field(default=60, ge=5, le=600)
    is_active: bool = True
    is_default: bool = False
    fallback_provider_id: uuid.UUID | None = None


class ProviderOut(ORM):
    id: uuid.UUID
    name: str
    kind: ProviderKind
    base_url: str | None
    api_version: str | None
    api_key_set: bool = False
    api_key_hint: str | None
    default_model: str
    temperature: float | None
    max_tokens: int
    timeout_seconds: int
    is_active: bool
    is_default: bool
    fallback_provider_id: uuid.UUID | None
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None


class PromptVersionOut(ORM):
    id: uuid.UUID
    version: int
    status: PromptStatus
    system_prompt: str
    user_template: str
    variables: list[str]
    output_format: str
    model: str | None
    notes: str | None
    created_at: datetime
    published_at: datetime | None


class PromptOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    category: str
    scope: str  # platform | tenant
    published_version: int | None
    effective: bool  # the version actually used by the pipeline for this tenant
    versions: list[PromptVersionOut]


class PromptVersionIn(BaseModel):
    system_prompt: str = Field(min_length=10, max_length=20000)
    user_template: str = Field(min_length=10, max_length=50000)
    model: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class PromptTestIn(BaseModel):
    version_id: uuid.UUID
    document_id: uuid.UUID
    provider_id: uuid.UUID | None = None
    model: str | None = Field(default=None, max_length=120)


class PromptTestOut(BaseModel):
    id: uuid.UUID
    ok: bool
    parsed: dict[str, Any] | None
    output_text: str | None
    error: str | None
    model: str | None
    provider: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    estimated_cost: Decimal | None
    credits: int | None
    created_at: datetime


class PriceIn(BaseModel):
    provider_kind: ProviderKind
    model: str = Field(min_length=1, max_length=120)
    input_per_mtok: Decimal = Field(ge=0)
    output_per_mtok: Decimal = Field(ge=0)
    effective_from: datetime | None = None


class PriceOut(ORM):
    id: uuid.UUID
    provider_kind: str
    model: str
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    currency: str
    effective_from: datetime
