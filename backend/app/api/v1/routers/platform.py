"""Platform (Super Admin "Pilot") endpoints: tenants, plans, platform metrics, audit integrity."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.database.session import get_db, set_session_tenant
from app.models import Document, Tenant, TenantModule, TenantQuota, TenantStatus, User
from app.schemas.platform import PlanOut, TenantCreate, TenantDetail, TenantOut, TenantStatusChange
from app.security.context import Principal, require_platform
from app.services import audit_service, tenant_service

router = APIRouter(prefix="/platform", tags=["Platform administration"])


def _platform_db(db: Session) -> Session:
    set_session_tenant(db, None, bypass_rls=True)
    return db


@router.get("/plans", response_model=list[PlanOut])
def list_plans(_: Principal = Depends(require_platform("platform:read")), db: Session = Depends(get_db)) -> list:
    from app.models import SubscriptionPlan

    _platform_db(db)
    return list(db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.max_users)))


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    _: Principal = Depends(require_platform("platform:read")), db: Session = Depends(get_db),
    status: TenantStatus | None = None, q: str | None = Query(default=None, max_length=100),
) -> list:
    _platform_db(db)
    stmt = select(Tenant).order_by(Tenant.created_at.desc())
    if status:
        stmt = stmt.where(Tenant.status == status)
    if q:
        stmt = stmt.where(Tenant.name.ilike(f"%{q}%") | Tenant.slug.ilike(f"%{q}%"))
    return list(db.scalars(stmt))


@router.post("/tenants", response_model=TenantDetail, status_code=201)
def create_tenant(body: TenantCreate, principal: Principal = Depends(require_platform("platform:administer")),
                  db: Session = Depends(get_db)) -> TenantDetail:
    _platform_db(db)
    result = tenant_service.provision_tenant(
        db, name=body.name, slug=body.slug, plan_code=body.plan_code, admin_email=body.admin_email,
        admin_full_name=body.admin_full_name, admin_password=body.admin_password,
        with_starter_types=body.with_starter_types,
    )
    principal.audit(db, "platform.tenant_created", tenant_id=None, resource_type="tenant",
                    resource_id=result.tenant.id, details={"slug": result.tenant.slug, "plan": body.plan_code,
                                                          "admin": result.admin.email})
    return _detail(db, result.tenant)


@router.get("/tenants/{tenant_id}", response_model=TenantDetail)
def get_tenant(tenant_id: uuid.UUID, _: Principal = Depends(require_platform("platform:read")),
               db: Session = Depends(get_db)) -> TenantDetail:
    _platform_db(db)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFound("Tenant not found")
    return _detail(db, tenant)


@router.post("/tenants/{tenant_id}/status", response_model=TenantDetail)
def change_status(tenant_id: uuid.UUID, body: TenantStatusChange,
                  principal: Principal = Depends(require_platform("platform:administer")),
                  db: Session = Depends(get_db)) -> TenantDetail:
    _platform_db(db)
    tenant = tenant_service.set_status(db, tenant_id, body.status)
    principal.audit(db, f"platform.tenant_{body.status.value}", tenant_id=None, resource_type="tenant",
                    resource_id=tenant.id, details={"reason": body.reason})
    return _detail(db, tenant)


@router.get("/metrics")
def platform_metrics(_: Principal = Depends(require_platform("platform:read")), db: Session = Depends(get_db)) -> dict:
    _platform_db(db)
    by_status = dict(db.execute(select(Tenant.status, func.count()).group_by(Tenant.status)).all())
    return {
        "tenants": {s.value: int(by_status.get(s, 0)) for s in TenantStatus},
        "users": int(db.scalar(select(func.count()).select_from(User)) or 0),
        "documents": int(db.scalar(select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))) or 0),
        "storage_bytes": int(db.scalar(select(func.coalesce(func.sum(Document.file_size), 0))) or 0),
    }


@router.get("/audit/verify")
def verify_audit_chain(tenant_id: uuid.UUID | None = None,
                       _: Principal = Depends(require_platform("platform:read")), db: Session = Depends(get_db)) -> dict:
    _platform_db(db)
    return audit_service.verify_chain(db, tenant_id)


def _detail(db: Session, tenant: Tenant) -> TenantDetail:
    quotas = {q.metric: q.limit_value for q in db.scalars(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))}
    modules = [m.module for m in db.scalars(select(TenantModule).where(TenantModule.tenant_id == tenant.id,
                                                                       TenantModule.enabled.is_(True)))]
    base = TenantOut.model_validate(tenant).model_dump()
    return TenantDetail(**base, usage=tenant_service.tenant_usage(db, tenant.id), quotas=quotas, modules=modules)
