"""Tenant membership & role administration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, QuotaExceeded, ValidationFailed
from app.models import MembershipStatus, Permission, Role, RolePermission, User, UserRole, UserTenant
from app.security.crypto import hash_password, validate_password_strength
from app.services import tenant_service


def _roles_by_code(db: Session, tenant_id: uuid.UUID, codes: list[str]) -> list[Role]:
    roles = list(db.scalars(select(Role).where(Role.tenant_id == tenant_id, Role.code.in_(codes))))
    missing = set(codes) - {r.code for r in roles}
    if missing:
        raise ValidationFailed("Unknown roles", details={"roles": sorted(missing)})
    return roles


def list_members(db: Session, tenant_id: uuid.UUID) -> list[tuple[UserTenant, list[Role]]]:
    memberships = db.scalars(select(UserTenant).where(UserTenant.tenant_id == tenant_id)).all()
    role_rows = db.execute(select(UserRole.user_id, Role).join(Role, Role.id == UserRole.role_id)
                           .where(UserRole.tenant_id == tenant_id)).all()
    by_user: dict[uuid.UUID, list[Role]] = {}
    for uid, role in role_rows:
        by_user.setdefault(uid, []).append(role)
    return sorted(((m, by_user.get(m.user_id, [])) for m in memberships), key=lambda x: x[0].user.full_name.lower())


def get_member(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> UserTenant:
    m = db.scalar(select(UserTenant).where(UserTenant.tenant_id == tenant_id, UserTenant.user_id == user_id))
    if m is None:
        raise NotFound("User not found in this organisation")
    return m


def _set_roles(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, codes: list[str]) -> None:
    roles = _roles_by_code(db, tenant_id, codes)
    current = {ur.role_id: ur for ur in db.scalars(select(UserRole).where(UserRole.tenant_id == tenant_id,
                                                                           UserRole.user_id == user_id))}
    wanted = {r.id for r in roles}
    for rid, ur in current.items():
        if rid not in wanted:
            db.delete(ur)
    for r in roles:
        if r.id not in current:
            db.add(UserRole(tenant_id=tenant_id, user_id=user_id, role_id=r.id))
    db.flush()


def _assert_admin_remains(db: Session, tenant_id: uuid.UUID) -> None:
    count = db.scalar(
        select(func.count()).select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .join(UserTenant, (UserTenant.user_id == UserRole.user_id) & (UserTenant.tenant_id == UserRole.tenant_id))
        .where(UserRole.tenant_id == tenant_id, Role.code == "tenant_admin",
               UserTenant.status == MembershipStatus.active)
    )
    if not count:
        raise ValidationFailed("The organisation must keep at least one active Tenant Admin", code="last_admin")


def add_member(db: Session, tenant_id: uuid.UUID, *, email: str, full_name: str, password: str | None,
               department: str | None, job_title: str | None, role_codes: list[str]) -> UserTenant:
    limit = tenant_service.get_quota(db, tenant_id, "users")
    if limit is not None and tenant_service.tenant_usage(db, tenant_id)["users"] >= limit:
        raise QuotaExceeded("User quota reached for this organisation", details={"limit": limit})
    _roles_by_code(db, tenant_id, role_codes)
    email = email.strip().lower()
    # Identity is global: look the user up outside tenant scope (users table has no RLS).
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        if password:
            validate_password_strength(password)
        user = User(email=email, full_name=full_name.strip(),
                    password_hash=hash_password(password) if password else None,
                    password_changed_at=datetime.now(UTC) if password else None)
        db.add(user)
        db.flush()
    elif db.scalar(select(UserTenant.id).where(UserTenant.tenant_id == tenant_id, UserTenant.user_id == user.id)):
        raise Conflict("This user is already a member of the organisation", code="already_member")
    membership = UserTenant(
        tenant_id=tenant_id, user_id=user.id, department=department, job_title=job_title,
        status=MembershipStatus.active if user.password_hash else MembershipStatus.invited,
    )
    db.add(membership)
    db.flush()
    _set_roles(db, tenant_id, user.id, role_codes)
    return membership


def update_member(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, actor_id: uuid.UUID, *,
                  full_name: str | None, status: MembershipStatus | None, department: str | None,
                  job_title: str | None, role_codes: list[str] | None) -> UserTenant:
    m = get_member(db, tenant_id, user_id)
    if status is not None and status != m.status:
        if user_id == actor_id and status == MembershipStatus.disabled:
            raise ValidationFailed("You cannot disable your own account")
        m.status = status
    if department is not None:
        m.department = department
    if job_title is not None:
        m.job_title = job_title
    if full_name:
        m.user.full_name = full_name.strip()
    if role_codes is not None:
        _set_roles(db, tenant_id, user_id, role_codes)
    db.flush()
    _assert_admin_remains(db, tenant_id)
    return m


def set_member_password(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, password: str) -> UserTenant:
    m = get_member(db, tenant_id, user_id)
    validate_password_strength(password)
    # A tenant admin may only set a password for accounts that belong exclusively to their tenant.
    other = db.scalar(select(func.count()).select_from(UserTenant).where(UserTenant.user_id == user_id,
                                                                         UserTenant.tenant_id != tenant_id))
    if other:
        raise ValidationFailed("This account belongs to several organisations; the user must reset it himself")
    m.user.password_hash = hash_password(password)
    m.user.password_changed_at = datetime.now(UTC)
    if m.status == MembershipStatus.invited:
        m.status = MembershipStatus.active
    db.flush()
    return m


def remove_member(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    if user_id == actor_id:
        raise ValidationFailed("You cannot remove yourself")
    m = get_member(db, tenant_id, user_id)
    for ur in db.scalars(select(UserRole).where(UserRole.tenant_id == tenant_id, UserRole.user_id == user_id)):
        db.delete(ur)
    db.delete(m)
    db.flush()
    _assert_admin_remains(db, tenant_id)


# ------------------------------------------------------------------ roles
def upsert_role(db: Session, tenant_id: uuid.UUID, *, role_id: uuid.UUID | None, code: str, name: str,
                description: str | None, permissions: list[str]) -> Role:
    valid = set(db.scalars(select(Permission.code)))
    unknown = set(permissions) - valid
    if unknown:
        raise ValidationFailed("Unknown permissions", details={"permissions": sorted(unknown)})
    if role_id:
        role = db.scalar(select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id))
        if role is None:
            raise NotFound("Role not found")
        if role.is_system and role.code == "tenant_admin":
            raise ValidationFailed("The Tenant Admin role cannot be modified")
    else:
        if db.scalar(select(Role.id).where(Role.tenant_id == tenant_id, Role.code == code)):
            raise Conflict("A role with this code already exists")
        role = Role(tenant_id=tenant_id, code=code, is_system=False, name=name)
        db.add(role)
        db.flush()
    role.name = name
    role.description = description
    role.permissions[:] = [p for p in role.permissions if p.permission_code in permissions]
    have = {p.permission_code for p in role.permissions}
    for perm in permissions:
        if perm not in have:
            role.permissions.append(RolePermission(tenant_id=tenant_id, permission_code=perm))
    db.flush()
    return role


def delete_role(db: Session, tenant_id: uuid.UUID, role_id: uuid.UUID) -> None:
    role = db.scalar(select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id))
    if role is None:
        raise NotFound("Role not found")
    if role.is_system:
        raise ValidationFailed("System roles cannot be deleted")
    if db.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)):
        raise Conflict("Role is still assigned to users")
    db.delete(role)
    db.flush()
