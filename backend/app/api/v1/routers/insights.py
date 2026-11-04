"""Dashboard KPIs, processing center and audit log — all computed from live data."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import AuditLog, Document, DocumentStatus, DocumentType, ProcessingJob, StepStatus
from app.schemas.common import Page
from app.security.context import Principal, require
from app.services import audit_service, tenant_service

router = APIRouter(tags=["Insights"])


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require("document:read")), db: Session = Depends(get_db)) -> dict:
    tid = p.tenant_id
    live = and_(Document.tenant_id == tid, Document.deleted_at.is_(None))
    by_status = dict(db.execute(select(Document.status, func.count()).where(live).group_by(Document.status)).all())
    by_type = db.execute(
        select(func.coalesce(DocumentType.name, "Non classé"), func.coalesce(DocumentType.color, "#94a3b8"), func.count())
        .select_from(Document).outerjoin(DocumentType, DocumentType.id == Document.document_type_id)
        .where(live).group_by(DocumentType.name, DocumentType.color).order_by(func.count().desc())
    ).all()
    since = datetime.now(UTC) - timedelta(days=29)
    day = func.date_trunc("day", Document.created_at)
    per_day = dict(db.execute(select(day, func.count()).where(Document.tenant_id == tid, Document.created_at >= since)
                              .group_by(day)).all())
    timeline = []
    for i in range(30):
        d = (since + timedelta(days=i)).date()
        count = next((c for k, c in per_day.items() if k.date() == d), 0)
        timeline.append({"date": d.isoformat(), "uploads": int(count)})
    ocr_avg = db.scalar(select(func.avg(ProcessingJob.duration_ms)).where(
        ProcessingJob.tenant_id == tid, ProcessingJob.step == "text_extraction",
        ProcessingJob.status == StepStatus.completed))
    failed_jobs = db.scalar(select(func.count()).select_from(ProcessingJob).where(
        ProcessingJob.tenant_id == tid, ProcessingJob.status == StepStatus.failed)) or 0
    usage = tenant_service.tenant_usage(db, tid)
    return {
        "documents_total": usage["documents"],
        "by_status": {s.value: int(by_status.get(s, 0)) for s in DocumentStatus},
        "by_type": [{"name": n, "color": c, "count": int(k)} for n, c, k in by_type],
        "uploads_last_30_days": timeline,
        "storage_bytes": usage["storage_bytes"],
        "storage_quota_bytes": tenant_service.get_quota(db, tid, "storage_bytes"),
        "users": usage["users"],
        "users_quota": tenant_service.get_quota(db, tid, "users"),
        "ocr_avg_ms": int(ocr_avg) if ocr_avg else None,
        "failed_jobs": int(failed_jobs),
        "pending_validation": int(by_status.get(DocumentStatus.pending_validation, 0)),
    }


@router.get("/processing/jobs")
def processing_jobs(
    p: Principal = Depends(require("processing:read")), db: Session = Depends(get_db),
    status: StepStatus | None = None, step: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = (select(ProcessingJob, Document.title).join(Document, Document.id == ProcessingJob.document_id)
            .where(ProcessingJob.tenant_id == p.tenant_id))
    if status:
        stmt = stmt.where(ProcessingJob.status == status)
    if step:
        stmt = stmt.where(ProcessingJob.step == step)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(ProcessingJob.updated_at.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    summary = dict(db.execute(select(ProcessingJob.status, func.count()).where(ProcessingJob.tenant_id == p.tenant_id)
                              .group_by(ProcessingJob.status)).all())
    return {
        "items": [{"id": j.id, "document_id": j.document_id, "document_title": title, "step": j.step,
                   "status": j.status, "attempts": j.attempts, "duration_ms": j.duration_ms, "error": j.error,
                   "result": j.result, "updated_at": j.updated_at, "version_number": j.version_number}
                  for j, title in rows],
        "total": int(total), "page": page, "page_size": page_size,
        "summary": {s.value: int(summary.get(s, 0)) for s in StepStatus},
    }


def _audit_query(p: Principal, action: str | None, actor: uuid.UUID | None, resource_id: str | None,
                 date_from: datetime | None, date_to: datetime | None):  # type: ignore[no-untyped-def]
    stmt = select(AuditLog).where(AuditLog.tenant_id == p.tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if actor:
        stmt = stmt.where(AuditLog.actor_user_id == actor)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return stmt.order_by(AuditLog.id.desc())


@router.get("/audit", response_model=Page[dict])
def audit_logs(
    p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db),
    action: str | None = None, actor: uuid.UUID | None = None, resource_id: str | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
) -> Page[dict]:
    stmt = _audit_query(p, action, actor, resource_id, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    items = [{"id": r.id, "created_at": r.created_at, "action": r.action, "actor_email": r.actor_email,
              "actor_user_id": r.actor_user_id, "resource_type": r.resource_type, "resource_id": r.resource_id,
              "outcome": r.outcome, "ip_address": r.ip_address, "details": r.details} for r in rows]
    return Page(items=items, total=int(total), page=page, page_size=page_size)


@router.get("/audit/export.csv")
def audit_export(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db),
                 action: str | None = None, date_from: datetime | None = None,
                 date_to: datetime | None = None) -> StreamingResponse:
    rows = db.scalars(_audit_query(p, action, None, None, date_from, date_to).limit(100_000)).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "action", "actor_email", "resource_type", "resource_id", "outcome", "ip", "hash"])
    for r in rows:
        writer.writerow([r.id, r.created_at.isoformat(), r.action, r.actor_email, r.resource_type, r.resource_id,
                         r.outcome, r.ip_address, r.hash])
    p.audit(db, "audit.exported", details={"rows": len(rows)})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit-log.csv"})


@router.get("/audit/verify")
def audit_verify(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)) -> dict:
    return audit_service.verify_chain(db, p.tenant_id)
