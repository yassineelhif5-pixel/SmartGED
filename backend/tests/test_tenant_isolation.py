"""Inter-tenant isolation: API layer *and* database RLS layer."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database.session import session_scope
from app.models import Document, Folder
from tests.conftest import auth


def _upload(client: TestClient, token: str, name: str = "secret.txt", body: bytes = b"confidential acme data") -> dict:
    r = client.post("/api/v1/documents", headers=auth(token), files={"file": (name, body, "text/plain")})
    assert r.status_code == 201, r.text
    return r.json()


def test_documents_are_invisible_across_tenants(client: TestClient, two_tenants: dict) -> None:
    doc = _upload(client, two_tenants["token_a"])
    tb = two_tenants["token_b"]
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=auth(tb)).status_code == 404
    assert client.get(f"/api/v1/documents/{doc['id']}/download", headers=auth(tb)).status_code == 404
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=auth(tb)).status_code == 404
    assert client.patch(f"/api/v1/documents/{doc['id']}", headers=auth(tb), json={"title": "pwned"}).status_code == 404
    listing = client.get("/api/v1/documents", headers=auth(tb)).json()
    assert listing["total"] == 0
    search = client.get("/api/v1/documents", params={"q": "confidential"}, headers=auth(tb)).json()
    assert search["total"] == 0


def test_cannot_attach_foreign_folder_or_type(client: TestClient, two_tenants: dict) -> None:
    ta, tb = two_tenants["token_a"], two_tenants["token_b"]
    folder_a = client.get("/api/v1/folders", headers=auth(ta)).json()[0]["id"]
    type_a = client.get("/api/v1/document-types", headers=auth(ta)).json()[0]["id"]
    r = client.post("/api/v1/documents", headers=auth(tb), data={"folder_id": folder_a},
                    files={"file": ("x.txt", b"hello there", "text/plain")})
    assert r.status_code == 404
    r = client.post("/api/v1/documents", headers=auth(tb), data={"document_type_id": type_a},
                    files={"file": ("x.txt", b"hello there", "text/plain")})
    assert r.status_code == 404
    doc_b = _upload(client, tb, body=b"globex stuff")
    r = client.post(f"/api/v1/documents/{doc_b['id']}/relations", headers=auth(tb),
                    json={"target_document_id": _upload(client, ta)["id"], "relation_type": "related"})
    assert r.status_code == 404


def test_users_and_audit_are_tenant_scoped(client: TestClient, two_tenants: dict) -> None:
    emails = {m["user"]["email"] for m in client.get("/api/v1/users", headers=auth(two_tenants["token_b"])).json()}
    assert emails == {"admin@globex.example.com"}
    _upload(client, two_tenants["token_a"])
    logs = client.get("/api/v1/audit", headers=auth(two_tenants["token_b"])).json()["items"]
    assert all(entry["action"] != "document.uploaded" for entry in logs)


def test_rls_blocks_reads_without_application_filter(client: TestClient, two_tenants: dict) -> None:
    """Even a query that forgets the tenant filter only sees the bound tenant's rows."""
    _upload(client, two_tenants["token_a"])
    tenant_b = uuid.UUID(two_tenants["b"]["id"])
    with session_scope(tenant_id=tenant_b) as db:
        assert db.scalars(select(Document)).all() == []
        assert {f.tenant_id for f in db.scalars(select(Folder))} == {tenant_b}
    with session_scope() as db:  # no tenant bound at all → nothing visible
        assert db.scalars(select(Document)).all() == []


def test_rls_blocks_cross_tenant_writes(client: TestClient, two_tenants: dict) -> None:
    tenant_a, tenant_b = uuid.UUID(two_tenants["a"]["id"]), uuid.UUID(two_tenants["b"]["id"])
    with pytest.raises(Exception, match="row-level security"):
        with session_scope(tenant_id=tenant_b) as db:
            db.add(Folder(tenant_id=tenant_a, name="injected"))
            db.flush()


def test_audit_log_is_append_only(client: TestClient, two_tenants: dict) -> None:
    _upload(client, two_tenants["token_a"])
    with pytest.raises(Exception, match="append-only"):
        with session_scope(bypass_rls=True) as db:
            db.execute(text("UPDATE audit_logs SET action = 'tampered'"))
    with pytest.raises(Exception, match="append-only"):
        with session_scope(bypass_rls=True) as db:
            db.execute(text("DELETE FROM audit_logs"))
    r = client.get("/api/v1/audit/verify", headers=auth(two_tenants["token_a"]))
    assert r.json()["valid"] is True


def test_forged_tenant_header_is_ignored(client: TestClient, two_tenants: dict) -> None:
    _upload(client, two_tenants["token_a"])
    r = client.get("/api/v1/documents", headers={**auth(two_tenants["token_b"]), "X-Tenant-ID": two_tenants["a"]["id"]},
                   params={"tenant_id": two_tenants["a"]["id"]})
    assert r.json()["total"] == 0
