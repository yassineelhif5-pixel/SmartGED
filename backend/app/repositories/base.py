"""Tenant-aware data access helpers.

Every lookup filters on ``tenant_id`` explicitly (defence in depth on top of
RLS). Fetching an object of another tenant behaves exactly like a missing
object (404), so ids cannot be probed across tenants.
"""

from __future__ import annotations

import uuid
from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound

M = TypeVar("M")


def get_owned(db: Session, model: type[M], tenant_id: uuid.UUID, obj_id: uuid.UUID, *,
              include_deleted: bool = False, label: str | None = None) -> M:
    stmt = select(model).where(model.id == obj_id, model.tenant_id == tenant_id)  # type: ignore[attr-defined]
    if hasattr(model, "deleted_at") and not include_deleted:
        stmt = stmt.where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
    obj = db.scalar(stmt)
    if obj is None:
        raise NotFound(f"{label or model.__name__} not found")
    return obj


def paginate(db: Session, stmt: Select, page: int, page_size: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).unique().all()
    return list(items), int(total)
