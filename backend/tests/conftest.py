"""Test fixtures: a real PostgreSQL database (RLS included), eager Celery, temp storage."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

os.environ.setdefault("DOCUMIND_DATABASE_URL", "postgresql+psycopg://documind:documind@localhost:5432/documind_test")
os.environ["DOCUMIND_ENVIRONMENT"] = "test"
os.environ["DOCUMIND_CELERY_EAGER"] = "true"
os.environ["DOCUMIND_SECURE_COOKIES"] = "false"
os.environ["DOCUMIND_SECRET_KEY"] = "test-secret-key-0123456789-abcdefghijklmnop"
os.environ["DOCUMIND_STORAGE_LOCAL_ROOT"] = tempfile.mkdtemp(prefix="documind-test-storage-")
os.environ["DOCUMIND_LOGIN_RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["DOCUMIND_AI_RETRY_BASE_SECONDS"] = "0"
os.environ["DOCUMIND_REDIS_URL"] = "redis://localhost:6379/15"
os.environ["DOCUMIND_BOOTSTRAP_ADMIN_EMAIL"] = "root@documind.example.com"
os.environ["DOCUMIND_BOOTSTRAP_ADMIN_PASSWORD"] = "RootPassw0rd!"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database.session import get_engine  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
PASSWORD = "Str0ngPassword!"


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))]
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    from app.core.rate_limit import reset_local

    reset_local()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str, password: str = PASSWORD, tenant_slug: str | None = None) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password, "tenant_slug": tenant_slug})
    assert r.status_code == 200, r.text
    return r.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def root_token(client: TestClient) -> str:
    return login(client, "root@documind.example.com", "RootPassw0rd!")["access_token"]


def make_tenant(client: TestClient, root_token: str, slug: str, admin_email: str) -> dict:
    r = client.post("/api/v1/platform/tenants", headers=auth(root_token), json={
        "name": slug.title(), "slug": slug, "plan_code": "business", "admin_email": admin_email,
        "admin_full_name": f"Admin {slug}", "admin_password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def two_tenants(client: TestClient, root_token: str) -> dict:
    a = make_tenant(client, root_token, "acme", "admin@acme.example.com")
    b = make_tenant(client, root_token, "globex", "admin@globex.example.com")
    return {
        "a": a, "b": b,
        "token_a": login(client, "admin@acme.example.com")["access_token"],
        "token_b": login(client, "admin@globex.example.com")["access_token"],
    }
