"""Shared (tenant) views administered by admins, personal views per user, default resolution."""

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, auth, login


def _member(client: TestClient, admin: str, email: str, role: str = "standard_user") -> str:
    r = client.post("/api/v1/users", headers=auth(admin), json={
        "email": email, "full_name": email.split("@")[0], "password": PASSWORD, "role_codes": [role]})
    assert r.status_code == 201, r.text
    return login(client, email)["access_token"]


def test_admin_shares_default_view_users_keep_their_own(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    invoice = next(t for t in client.get("/api/v1/document-types", headers=auth(admin)).json() if t["code"] == "invoice")
    shared = client.post("/api/v1/document-views", headers=auth(admin), json={
        "name": "Factures à valider", "scope": "tenant", "is_default": True,
        "filters": {"document_type_id": invoice["id"], "status": "pending_validation", "sort": "created_at"}})
    assert shared.status_code == 201, shared.text

    user = _member(client, admin, "alice@acme.example.com")
    listing = client.get("/api/v1/document-views", headers=auth(user)).json()
    assert listing["default_view_id"] == shared.json()["id"] and listing["default_source"] == "tenant"
    assert listing["views"][0]["can_edit"] is False

    # a standard user cannot create, edit or delete shared views
    r = client.post("/api/v1/document-views", headers=auth(user),
                    json={"name": "x", "scope": "tenant", "filters": {}})
    assert r.status_code == 403
    r = client.put(f"/api/v1/document-views/{shared.json()['id']}", headers=auth(user),
                   json={"name": "hacked", "scope": "tenant", "filters": {}})
    assert r.status_code == 403
    assert client.delete(f"/api/v1/document-views/{shared.json()['id']}", headers=auth(user)).status_code == 403

    # … but can save personal views and pick their own default
    mine = client.post("/api/v1/document-views", headers=auth(user), json={
        "name": "Mes contrats", "filters": {"mine": True, "q": "contrat", "meta": {"counterparty": "Nova"}}}).json()
    assert mine["scope"] == "personal" and mine["is_mine"] and mine["can_edit"]
    client.put("/api/v1/document-views/me/default", headers=auth(user), json={"view_id": mine["id"]})
    listing = client.get("/api/v1/document-views", headers=auth(user)).json()
    assert listing["default_view_id"] == mine["id"] and listing["default_source"] == "user"
    client.delete("/api/v1/document-views/me/default", headers=auth(user))
    assert client.get("/api/v1/document-views", headers=auth(user)).json()["default_source"] == "tenant"


def test_personal_views_are_private(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    alice = _member(client, admin, "alice@acme.example.com")
    bob = _member(client, admin, "bob@acme.example.com")
    view = client.post("/api/v1/document-views", headers=auth(alice), json={"name": "Privé", "filters": {}}).json()
    assert all(v["id"] != view["id"] for v in client.get("/api/v1/document-views", headers=auth(bob)).json()["views"])
    assert client.put(f"/api/v1/document-views/{view['id']}", headers=auth(bob),
                      json={"name": "x", "filters": {}}).status_code == 404
    assert client.put("/api/v1/document-views/me/default", headers=auth(bob),
                      json={"view_id": view["id"]}).status_code == 404
    # even the tenant admin does not see someone else's personal view
    assert all(v["id"] != view["id"] for v in client.get("/api/v1/document-views", headers=auth(admin)).json()["views"])
    # other tenants never see anything
    assert client.get("/api/v1/document-views", headers=auth(two_tenants["token_b"])).json()["views"] == []


def test_only_one_shared_default_and_foreign_ids_rejected(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    a = client.post("/api/v1/document-views", headers=auth(admin),
                    json={"name": "A", "scope": "tenant", "is_default": True, "filters": {}}).json()
    b = client.post("/api/v1/document-views", headers=auth(admin),
                    json={"name": "B", "scope": "tenant", "is_default": True, "filters": {}}).json()
    views = {v["id"]: v for v in client.get("/api/v1/document-views", headers=auth(admin)).json()["views"]}
    assert views[b["id"]]["is_default"] and not views[a["id"]]["is_default"]
    foreign_folder = client.get("/api/v1/folders", headers=auth(two_tenants["token_b"])).json()[0]["id"]
    r = client.post("/api/v1/document-views", headers=auth(admin),
                    json={"name": "x", "filters": {"folder_id": foreign_folder}})
    assert r.status_code == 404


def test_mine_filter(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    alice = _member(client, admin, "alice@acme.example.com")
    client.post("/api/v1/documents", headers=auth(admin), files={"file": ("a.txt", b"admin file text", "text/plain")})
    client.post("/api/v1/documents", headers=auth(alice), files={"file": ("b.txt", b"alice file text", "text/plain")})
    assert client.get("/api/v1/documents", headers=auth(alice)).json()["total"] == 2
    mine = client.get("/api/v1/documents", params={"mine": True}, headers=auth(alice)).json()
    assert mine["total"] == 1 and mine["items"][0]["title"] == "b"
