"""Append-only, hash-chained audit trail.

Each row's hash covers its content plus the previous row's hash for the same
tenant (or the platform chain), so any later tampering breaks the chain and is
detectable with :func:`verify_chain`. UPDATE/DELETE are rejected by a DB trigger.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models import AuditLog


def _digest(prev_hash: str | None, payload: dict[str, Any]) -> str:
    raw = (prev_hash or "") + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def record(
    db: Session,
    *,
    action: str,
    tenant_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | uuid.UUID | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    # Serialise writers of the same chain to keep prev_hash consistent.
    chain_key = str(tenant_id) if tenant_id else "platform"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{chain_key}"})
    prev = db.scalar(
        select(AuditLog.hash)
        .where(AuditLog.tenant_id.is_(None) if tenant_id is None else AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    created_at = datetime.now(UTC)
    payload = {
        "tenant_id": str(tenant_id) if tenant_id else None,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "action": action,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id else None,
        "outcome": outcome,
        "details": details,
        "created_at": created_at.isoformat(),
    }
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        outcome=outcome,
        details=details,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:400] or None,
        request_id=request_id_var.get(),
        prev_hash=prev,
        hash=_digest(prev, payload),
        created_at=created_at,
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session, tenant_id: uuid.UUID | None) -> dict[str, Any]:
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id.is_(None) if tenant_id is None else AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.id)
    ).all()
    prev: str | None = None
    for row in rows:
        payload = {
            "tenant_id": str(row.tenant_id) if row.tenant_id else None,
            "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "outcome": row.outcome,
            "details": row.details,
            "created_at": row.created_at.astimezone(UTC).isoformat(),
        }
        if row.prev_hash != prev or row.hash != _digest(prev, payload):
            return {"valid": False, "broken_at_id": row.id, "checked": len(rows)}
        prev = row.hash
    return {"valid": True, "broken_at_id": None, "checked": len(rows)}
