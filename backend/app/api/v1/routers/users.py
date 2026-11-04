"""Tenant administration: members and roles."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.database.session import get_db
from app.models import Permission, Role
from app.schemas.common import Message
from app.schemas.identity import MemberCreate, MemberOut, MemberUpdate, RoleBrief, RoleOut, RoleUpsert, UserOut
from app.security.context import Principal, require
from app.services import user_service

router = APIRouter(tags=["Users & roles"])


def _assert_can_grant(db: Session, p: Principal, role_codes: list[str]) -> None:
    """Anti-escalation: without user:administer you may only grant roles whose
    permissions are a subset of your own."""
    if p.can("user:administer"):
        return
    roles = db.scalars(select(Role).where(Role.tenant_id == p.tenant_id, Role.code.in_(role_codes))).all()
    for role in roles:
        extra = {rp.permission_code for rp in role.permissions} - p.permissions
        if extra:
            raise Forbidden(f"You cannot grant the role '{role.code}'", code="privilege_escalation",
                            details={"exceeding_permissions": sorted(extra)})


def _member_out(m, roles) -> MemberOut:  # type: ignore[no-untyped-def]
    return MemberOut(user=UserOut.model_validate(m.user), status=m.status, department=m.department,
                     job_title=m.job_title, roles=[RoleBrief.model_validate(r) for r in roles], joined_at=m.created_at)


@router.get("/users", response_model=list[MemberOut])
def list_users(p: Principal = Depends(require("user:read")), db: Session = Depends(get_db)) -> list[MemberOut]:
    return [_member_out(m, roles) for m, roles in user_service.list_members(db, p.tenant_id)]


@router.post("/users", response_model=MemberOut, status_code=201)
def create_user(body: MemberCreate, p: Principal = Depends(require("user:create")),
                db: Session = Depends(get_db)) -> MemberOut:
    _assert_can_grant(db, p, body.role_codes)
    m = user_service.add_member(db, p.tenant_id, email=body.email, full_name=body.full_name, password=body.password,
                                department=body.department, job_title=body.job_title, role_codes=body.role_codes)
    p.audit(db, "user.added", resource_type="user", resource_id=m.user_id,
            details={"email": m.user.email, "roles": body.role_codes})
    roles = dict((mm.user_id, r) for mm, r in user_service.list_members(db, p.tenant_id))
    return _member_out(m, roles.get(m.user_id, []))


@router.patch("/users/{user_id}", response_model=MemberOut)
def update_user(user_id: uuid.UUID, body: MemberUpdate, p: Principal = Depends(require("user:update")),
                db: Session = Depends(get_db)) -> MemberOut:
    if body.role_codes is not None:
        _assert_can_grant(db, p, body.role_codes)
    m = user_service.update_member(db, p.tenant_id, user_id, p.user.id, full_name=body.full_name, status=body.status,
                                   department=body.department, job_title=body.job_title, role_codes=body.role_codes)
    p.audit(db, "user.updated", resource_type="user", resource_id=user_id,
            details=body.model_dump(exclude_none=True, mode="json"))
    roles = dict((mm.user_id, r) for mm, r in user_service.list_members(db, p.tenant_id))
    return _member_out(m, roles.get(user_id, []))


class SetPassword(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.post("/users/{user_id}/password", response_model=Message)
def set_password(user_id: uuid.UUID, body: SetPassword, p: Principal = Depends(require("user:administer")),
                 db: Session = Depends(get_db)) -> Message:
    user_service.set_member_password(db, p.tenant_id, user_id, body.password)
    p.audit(db, "user.password_set_by_admin", resource_type="user", resource_id=user_id)
    return Message(message="Password updated")


@router.delete("/users/{user_id}", response_model=Message)
def remove_user(user_id: uuid.UUID, p: Principal = Depends(require("user:delete")),
                db: Session = Depends(get_db)) -> Message:
    user_service.remove_member(db, p.tenant_id, user_id, p.user.id)
    p.audit(db, "user.removed", resource_type="user", resource_id=user_id)
    return Message(message="User removed from the organisation")


# ------------------------------------------------------------------ roles
def _assert_subset(p: Principal, permissions: list[str]) -> None:
    extra = set(permissions) - p.permissions
    if extra:
        raise Forbidden("A role cannot hold permissions you do not have", code="privilege_escalation",
                        details={"exceeding_permissions": sorted(extra)})


def _role_out(role: Role) -> RoleOut:
    return RoleOut(id=role.id, code=role.code, name=role.name, description=role.description,
                   is_system=role.is_system, permissions=sorted(p.permission_code for p in role.permissions))


@router.get("/roles", response_model=list[RoleOut])
def list_roles(p: Principal = Depends(require("role:read")), db: Session = Depends(get_db)) -> list[RoleOut]:
    return [_role_out(r) for r in db.scalars(select(Role).where(Role.tenant_id == p.tenant_id).order_by(Role.name))]


@router.get("/permissions")
def list_permissions(p: Principal = Depends(require("role:read")), db: Session = Depends(get_db)) -> list[dict]:
    return [{"code": x.code, "resource": x.resource, "action": x.action}
            for x in db.scalars(select(Permission).order_by(Permission.resource, Permission.action))]


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(body: RoleUpsert, p: Principal = Depends(require("role:create")),
                db: Session = Depends(get_db)) -> RoleOut:
    _assert_subset(p, body.permissions)
    role = user_service.upsert_role(db, p.tenant_id, role_id=None, code=body.code, name=body.name,
                                    description=body.description, permissions=body.permissions)
    p.audit(db, "role.created", resource_type="role", resource_id=role.id, details={"permissions": body.permissions})
    return _role_out(role)


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: uuid.UUID, body: RoleUpsert, p: Principal = Depends(require("role:update")),
                db: Session = Depends(get_db)) -> RoleOut:
    _assert_subset(p, body.permissions)
    role = user_service.upsert_role(db, p.tenant_id, role_id=role_id, code=body.code, name=body.name,
                                    description=body.description, permissions=body.permissions)
    p.audit(db, "role.permissions_changed", resource_type="role", resource_id=role.id,
            details={"permissions": body.permissions})
    return _role_out(role)


@router.delete("/roles/{role_id}", response_model=Message)
def delete_role(role_id: uuid.UUID, p: Principal = Depends(require("role:delete")),
                db: Session = Depends(get_db)) -> Message:
    user_service.delete_role(db, p.tenant_id, role_id)
    p.audit(db, "role.deleted", resource_type="role", resource_id=role_id)
    return Message(message="Role deleted")
