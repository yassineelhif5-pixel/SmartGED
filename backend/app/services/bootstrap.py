"""Idempotent startup bootstrap: permission catalogue, plans, default settings, first Super Admin."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.session import session_scope
from app.models import PlatformRole, Tenant, User
from app.security.crypto import hash_password, validate_password_strength
from app.services import tenant_service

log = get_logger(__name__)


def bootstrap() -> None:
    settings = get_settings()
    with session_scope(bypass_rls=True) as db:
        tenant_service.ensure_platform_defaults(db)
        for tenant in db.scalars(select(Tenant)).all():
            tenant_service.ensure_system_roles(db, tenant.id)  # propagate new permissions to system roles
        if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
            email = settings.bootstrap_admin_email.lower()
            if db.scalar(select(User).where(User.email == email)) is None:
                validate_password_strength(settings.bootstrap_admin_password)
                db.add(User(email=email, full_name="Platform Administrator",
                            password_hash=hash_password(settings.bootstrap_admin_password),
                            platform_role=PlatformRole.super_admin, password_changed_at=datetime.now(UTC)))
                log.info("bootstrap_super_admin_created", extra={"email": email})
