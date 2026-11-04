"""Database engine, sessions and tenant-scoped Row Level Security context.

Isolation is enforced twice:
1. Application layer: every repository/service filters on ``tenant_id``.
2. Database layer: PostgreSQL RLS policies compare ``tenant_id`` with the
   transaction-local GUC ``app.tenant_id``. The GUC is (re)applied at the
   beginning of *every* transaction from ``session.info`` so that commits inside
   a request never drop the tenant context.

Platform-level operations (tenant provisioning, login lookups across tenants)
explicitly open a session with ``bypass_rls=True``; this is never driven by
user input.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionFactory
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            future=True,
        )
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def _factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


@event.listens_for(Session, "after_begin")
def _apply_rls_context(session: Session, transaction: object, connection: object) -> None:
    tenant_id = session.info.get("tenant_id")
    bypass = session.info.get("bypass_rls", False)
    connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT set_config('app.tenant_id', :tid, true), "
            "set_config('app.bypass_rls', :bypass, true)"
        ),
        {"tid": str(tenant_id) if tenant_id else "", "bypass": "on" if bypass else "off"},
    )


def new_session(*, tenant_id: UUID | None = None, bypass_rls: bool = False) -> Session:
    session = _factory()()
    session.info["tenant_id"] = tenant_id
    session.info["bypass_rls"] = bypass_rls
    return session


def set_session_tenant(session: Session, tenant_id: UUID | None, *, bypass_rls: bool = False) -> None:
    """Bind a session to a tenant. Takes effect for the current *and* future transactions."""
    session.info["tenant_id"] = tenant_id
    session.info["bypass_rls"] = bypass_rls
    if session.in_transaction():
        session.execute(
            text(
                "SELECT set_config('app.tenant_id', :tid, true), "
                "set_config('app.bypass_rls', :bypass, true)"
            ),
            {"tid": str(tenant_id) if tenant_id else "", "bypass": "on" if bypass_rls else "off"},
        )


@contextmanager
def session_scope(*, tenant_id: UUID | None = None, bypass_rls: bool = False) -> Iterator[Session]:
    session = new_session(tenant_id=tenant_id, bypass_rls=bypass_rls)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a request-scoped session with no tenant bound yet."""
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
