from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import MembershipStatus, PlatformRole, TenantStatus
from app.schemas.common import ORM


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    tenant_slug: str | None = Field(default=None, max_length=63)


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class TenantBrief(ORM):
    id: uuid.UUID
    slug: str
    name: str
    status: TenantStatus


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    platform_role: PlatformRole | None
    is_active: bool
    locale: str
    last_login_at: datetime | None


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    tenant: TenantBrief | None
    tenants: list[TenantBrief]
    permissions: list[str]
    platform_capabilities: list[str]


class RoleBrief(ORM):
    id: uuid.UUID
    code: str
    name: str


class MemberOut(BaseModel):
    user: UserOut
    status: MembershipStatus
    department: str | None
    job_title: str | None
    roles: list[RoleBrief]
    joined_at: datetime


class MemberCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    role_codes: list[str] = Field(default_factory=lambda: ["standard_user"])


class MemberUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    status: MembershipStatus | None = None
    department: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    role_codes: list[str] | None = None


class RoleOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[str]


class RoleUpsert(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,59}$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str]


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=200)
