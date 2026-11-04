"""Liveness / readiness probes and capability status (what is configured, what is not)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.ocr.engine import get_ocr_provider

router = APIRouter(tags=["Health"])


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    settings = get_settings()
    redis_ok = False
    try:
        import redis

        redis_ok = bool(redis.Redis.from_url(settings.redis_url, socket_timeout=0.5).ping())
    except Exception:  # noqa: BLE001
        redis_ok = False
    ocr = get_ocr_provider()
    return {
        "status": "ok",
        "database": "ok",
        "redis": "ok" if redis_ok else "unavailable",
        "capabilities": {
            "storage": settings.storage_provider,
            "ocr": ocr.name if ocr else "not_configured",
            "antivirus": "clamav" if settings.clamav_host else "not_configured",
            "ai": "not_configured",
        },
        "environment": settings.environment,
    }
