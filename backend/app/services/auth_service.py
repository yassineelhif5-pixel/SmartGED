"""Authentication: login, refresh-token rotation, logout, tenant switching."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, Unauthorized
from app.core.rate_limit import hit
from app.models import MembershipStatus, Tenant, TenantStatus, User, UserSession, UserTenant
from app.security.crypto import create_access_token, new_refresh_token, sha256_hex, verify_password
from app.services import audit_service


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    session: UserSession
    user: User
    tenant: Tenant | None


def active_memberships(db: Session, user_id: uuid.UUID) -> list[tuple[UserTenant, Tenant]]:
    rows = db.execute(
        select(UserTenant, Tenant)
        .join(Tenant, Tenant.id == UserTenant.tenant_id)
        .where(
            UserTenant.user_id == user_id,
            UserTenant.status == MembershipStatus.active,
            Tenant.status == TenantStatus.active,
        )
        .order_by(Tenant.name)
    ).all()
    return [(m, t) for m, t in rows]


def _pick_tenant(db: Session, user: User, tenant_slug: str | None) -> Tenant | None:
    memberships = active_memberships(db, user.id)
    if tenant_slug:
        for _, tenant in memberships:
            if tenant.slug == tenant_slug.lower():
                return tenant
        raise Forbidden("No access to this organisation", code="tenant_access_denied")
    if memberships:
        return memberships[0][1]
    if user.platform_role is None:
        raise Forbidden("Your account is not attached to any active organisation", code="no_tenant")
    return None  # platform staff without tenant membership


def login(
    db: Session, *, email: str, password: str, tenant_slug: str | None, ip: str | None, user_agent: str | None
) -> IssuedTokens:
    """Must be called with a bypass-RLS session (identity is cross-tenant)."""
    settings = get_settings()
    email = email.strip().lower()
    hit(f"login:ip:{ip}", settings.login_rate_limit_per_minute * 3)
    hit(f"login:email:{email}", settings.login_rate_limit_per_minute)

    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(password, user.password_hash if user else None) or user is None or not user.is_active:
        audit_service.record(db, action="auth.login", tenant_id=None, actor_email=email, outcome="failure",
                             ip_address=ip, user_agent=user_agent, details={"reason": "invalid_credentials"})
        db.commit()  # keep the failed-attempt trail even though the request fails
        raise Unauthorized("Invalid email or password", code="invalid_credentials")

    tenant = _pick_tenant(db, user, tenant_slug)
    issued = _issue(db, user, tenant, ip, user_agent)
    user.last_login_at = datetime.now(UTC)
    audit_service.record(db, action="auth.login", tenant_id=tenant.id if tenant else None, actor_user_id=user.id,
                         actor_email=user.email, ip_address=ip, user_agent=user_agent)
    return issued


def _issue(db: Session, user: User, tenant: Tenant | None, ip: str | None, user_agent: str | None) -> IssuedTokens:
    token, token_hash = new_refresh_token()
    session = UserSession(
        user_id=user.id,
        tenant_id=tenant.id if tenant else None,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_ttl_days),
        ip_address=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    db.add(session)
    db.flush()
    access = create_access_token(user.id, tenant.id if tenant else None, session.id)
    return IssuedTokens(access_token=access, refresh_token=token, session=session, user=user, tenant=tenant)


def refresh(db: Session, *, refresh_token: str, ip: str | None, user_agent: str | None) -> IssuedTokens:
    """Rotate a refresh token. Re-use of a revoked token revokes all of the user's sessions."""
    session = db.scalar(select(UserSession).where(UserSession.token_hash == sha256_hex(refresh_token)))
    if session is None:
        raise Unauthorized("Invalid refresh token", code="invalid_refresh")
    now = datetime.now(UTC)
    if session.revoked_at is not None:
        # Token replay → likely theft: kill every active session of this user.
        for s in db.scalars(select(UserSession).where(UserSession.user_id == session.user_id,
                                                      UserSession.revoked_at.is_(None))):
            s.revoked_at = now
        audit_service.record(db, action="auth.refresh_reuse_detected", tenant_id=session.tenant_id,
                             actor_user_id=session.user_id, outcome="failure", ip_address=ip)
        db.commit()  # revocations must persist even though the request fails
        raise Unauthorized("Refresh token reuse detected", code="refresh_reuse")
    if session.expires_at < now:
        raise Unauthorized("Session expired", code="session_expired")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("User inactive")
    tenant: Tenant | None = None
    if session.tenant_id:
        valid = {t.id: t for _, t in active_memberships(db, user.id)}
        tenant = valid.get(session.tenant_id)
        if tenant is None:
            raise Forbidden("No access to this tenant anymore", code="tenant_access_denied")
    session.revoked_at = now
    return _issue(db, user, tenant, ip, user_agent)


def switch_tenant(db: Session, *, user: User, session_id: uuid.UUID, tenant_id: uuid.UUID,
                  ip: str | None, user_agent: str | None) -> IssuedTokens:
    valid = {t.id: t for _, t in active_memberships(db, user.id)}
    tenant = valid.get(tenant_id)
    if tenant is None:
        raise Forbidden("No access to this tenant", code="tenant_access_denied")
    old = db.get(UserSession, session_id)
    if old is not None:
        old.revoked_at = datetime.now(UTC)
    issued = _issue(db, user, tenant, ip, user_agent)
    audit_service.record(db, action="auth.switch_tenant", tenant_id=tenant.id, actor_user_id=user.id,
                         actor_email=user.email, ip_address=ip)
    return issued


def logout(db: Session, *, session_id: uuid.UUID) -> None:
    session = db.get(UserSession, session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
