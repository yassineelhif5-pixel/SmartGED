"""Request security context: authenticated user, verified active tenant, effective permissions.

The active tenant is taken from the signed access token and *re-verified*
against an active membership on every request. A tenant id sent by the client
(header, body or query) is never trusted.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.logging import tenant_id_var
from app.database.session import get_db, set_session_tenant
from app.models import (
    MembershipStatus,
    RolePermission,
    Tenant,
    TenantStatus,
    User,
    UserRole,
    UserSession,
    UserTenant,
)
from app.security.crypto import decode_access_token
from app.security.permissions import PLATFORM_CAPABILITIES
from app.services import audit_service

_bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user: User
    session_id: uuid.UUID
    tenant: Tenant | None
    permissions: set[str] = field(default_factory=set)
    ip: str | None = None
    user_agent: str | None = None

    @property
    def tenant_id(self) -> uuid.UUID:
        if self.tenant is None:
            raise Forbidden("No active tenant for this session", code="no_tenant")
        return self.tenant.id

    @property
    def platform_capabilities(self) -> set[str]:
        role = self.user.platform_role
        return PLATFORM_CAPABILITIES.get(role.value, set()) if role else set()

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def audit(self, db: Session, action: str, **kwargs: object) -> None:
        audit_service.record(
            db,
            action=action,
            tenant_id=kwargs.pop("tenant_id", self.tenant.id if self.tenant else None),  # type: ignore[arg-type]
            actor_user_id=self.user.id,
            actor_email=self.user.email,
            ip_address=self.ip,
            user_agent=self.user_agent,
            **kwargs,  # type: ignore[arg-type]
        )


def load_permissions(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> set[str]:
    rows = db.scalars(
        select(RolePermission.permission_code)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id, UserRole.tenant_id == tenant_id)
    ).all()
    return set(rows)


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Authentication required")
    claims = decode_access_token(credentials.credentials)

    # Identity lookups are cross-tenant by nature: use a platform-bypass context briefly.
    set_session_tenant(db, None, bypass_rls=True)
    user = db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("User inactive or unknown")
    session = db.get(UserSession, claims.session_id)
    if session is None or session.revoked_at is not None or session.user_id != user.id:
        raise Unauthorized("Session revoked", code="session_revoked")

    tenant: Tenant | None = None
    permissions: set[str] = set()
    if claims.tenant_id is not None:
        tenant = db.get(Tenant, claims.tenant_id)
        membership = db.scalar(
            select(UserTenant).where(
                UserTenant.tenant_id == claims.tenant_id, UserTenant.user_id == user.id
            )
        )
        if tenant is None or membership is None or membership.status != MembershipStatus.active:
            raise Forbidden("No access to this tenant", code="tenant_access_denied")
        if tenant.status != TenantStatus.active:
            raise Forbidden(f"Tenant is {tenant.status.value}", code="tenant_inactive")
        permissions = load_permissions(db, tenant.id, user.id)

    # From here on, the session is strictly bound to the verified tenant (RLS enforced).
    set_session_tenant(db, tenant.id if tenant else None, bypass_rls=False)
    tenant_id_var.set(str(tenant.id) if tenant else None)

    return Principal(
        user=user,
        session_id=claims.session_id,
        tenant=tenant,
        permissions=permissions,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def require(*permissions: str) -> Callable[[Principal], Principal]:
    """Dependency factory: the principal must hold *all* the listed tenant permissions."""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        principal.tenant_id  # noqa: B018 — raises if no tenant
        missing = [p for p in permissions if p not in principal.permissions]
        if missing:
            raise Forbidden("Missing permission", details={"missing": missing}, code="permission_denied")
        return principal

    return _dep


def require_platform(capability: str) -> Callable[[Principal], Principal]:
    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if capability not in principal.platform_capabilities:
            raise Forbidden("Platform privilege required", code="platform_denied")
        return principal

    return _dep
