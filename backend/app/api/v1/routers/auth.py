"""Authentication endpoints. The refresh token lives in an httpOnly, SameSite=strict cookie."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Unauthorized, ValidationFailed
from app.database.session import get_db, set_session_tenant
from app.schemas.common import Message
from app.schemas.identity import (
    ChangePasswordRequest,
    LoginRequest,
    SessionOut,
    SwitchTenantRequest,
    TenantBrief,
    UserOut,
)
from app.security.context import Principal, get_principal, load_permissions
from app.security.crypto import hash_password, validate_password_strength, verify_password
from app.services import audit_service, auth_service
from app.services.auth_service import IssuedTokens

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE = "documind_refresh"


def _client(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE, token, httponly=True, secure=settings.secure_cookies, samesite="strict",
        max_age=settings.refresh_token_ttl_days * 86400, path=f"{settings.api_prefix}/auth",
    )


def _session_payload(db: Session, issued: IssuedTokens) -> SessionOut:
    from app.security.permissions import PLATFORM_CAPABILITIES

    memberships = auth_service.active_memberships(db, issued.user.id)
    perms = sorted(load_permissions(db, issued.tenant.id, issued.user.id)) if issued.tenant else []
    role = issued.user.platform_role
    return SessionOut(
        access_token=issued.access_token,
        expires_in=get_settings().access_token_ttl_minutes * 60,
        user=UserOut.model_validate(issued.user),
        tenant=TenantBrief.model_validate(issued.tenant) if issued.tenant else None,
        tenants=[TenantBrief.model_validate(t) for _, t in memberships],
        permissions=perms,
        platform_capabilities=sorted(PLATFORM_CAPABILITIES.get(role.value, set()) if role else set()),
    )


@router.post("/login", response_model=SessionOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    set_session_tenant(db, None, bypass_rls=True)
    ip, ua = _client(request)
    issued = auth_service.login(db, email=body.email, password=body.password, tenant_slug=body.tenant_slug,
                                ip=ip, user_agent=ua)
    _set_cookie(response, issued.refresh_token)
    return _session_payload(db, issued)


@router.post("/refresh", response_model=SessionOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db),
            refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)) -> SessionOut:
    if not refresh_token:
        raise Unauthorized("No session", code="no_session")
    set_session_tenant(db, None, bypass_rls=True)
    ip, ua = _client(request)
    issued = auth_service.refresh(db, refresh_token=refresh_token, ip=ip, user_agent=ua)
    _set_cookie(response, issued.refresh_token)
    return _session_payload(db, issued)


@router.post("/switch-tenant", response_model=SessionOut)
def switch_tenant(body: SwitchTenantRequest, request: Request, response: Response,
                  principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> SessionOut:
    set_session_tenant(db, None, bypass_rls=True)
    ip, ua = _client(request)
    issued = auth_service.switch_tenant(db, user=principal.user, session_id=principal.session_id,
                                        tenant_id=body.tenant_id, ip=ip, user_agent=ua)
    _set_cookie(response, issued.refresh_token)
    return _session_payload(db, issued)


@router.post("/logout", response_model=Message)
def logout(response: Response, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> Message:
    set_session_tenant(db, None, bypass_rls=True)
    auth_service.logout(db, session_id=principal.session_id)
    audit_service.record(db, action="auth.logout", tenant_id=principal.tenant.id if principal.tenant else None,
                         actor_user_id=principal.user.id, actor_email=principal.user.email, ip_address=principal.ip)
    response.delete_cookie(REFRESH_COOKIE, path=f"{get_settings().api_prefix}/auth")
    return Message(message="Logged out")


@router.get("/me", response_model=UserOut)
def me(principal: Principal = Depends(get_principal)) -> UserOut:
    return UserOut.model_validate(principal.user)


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordRequest, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)) -> Message:
    from datetime import UTC, datetime

    user = principal.user
    if not verify_password(body.current_password, user.password_hash):
        raise ValidationFailed("Current password is incorrect", code="invalid_password")
    validate_password_strength(body.new_password)
    set_session_tenant(db, None, bypass_rls=True)
    user = db.merge(user)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(UTC)
    audit_service.record(db, action="auth.password_changed", tenant_id=principal.tenant.id if principal.tenant else None,
                         actor_user_id=user.id, actor_email=user.email, ip_address=principal.ip)
    return Message(message="Password updated")
