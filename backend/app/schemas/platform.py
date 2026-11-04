from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import TenantStatus
from app.schemas.common import ORM


class PlanOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    max_users: int
    max_storage_bytes: int
    monthly_ai_credits: int
    modules: list[str]
    is_active: bool


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=3, max_length=63)
    plan_code: str = "business"
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=200)
    admin_password: str | None = Field(default=None, max_length=200)
    with_starter_types: bool = True


class TenantOut(ORM):
    id: uuid.UUID
    slug: str
    name: str
    status: TenantStatus
    storage_provider: str
    created_at: datetime
    suspended_at: datetime | None
    plan: PlanOut | None


class TenantDetail(TenantOut):
    usage: dict[str, int]
    quotas: dict[str, int]
    modules: list[str]


class TenantStatusChange(BaseModel):
    status: TenantStatus
    reason: str | None = Field(default=None, max_length=500)
