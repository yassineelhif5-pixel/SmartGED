from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, auth, login


def test_login_wrong_password_is_rejected_and_audited(client: TestClient, two_tenants: dict) -> None:
    r = client.post("/api/v1/auth/login", json={"email": "admin@acme.example.com", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"
    platform = login(client, "root@documind.example.com", "RootPassw0rd!")["access_token"]
    assert client.get("/api/v1/platform/audit/verify", headers=auth(platform)).json()["valid"] is True


def test_login_returns_tenant_and_permissions(client: TestClient, two_tenants: dict) -> None:
    s = login(client, "admin@acme.example.com")
    assert s["tenant"]["slug"] == "acme"
    assert "document:create" in s["permissions"]
    assert s["platform_capabilities"] == []


def test_refresh_rotation_and_reuse_detection(client: TestClient, two_tenants: dict) -> None:
    login(client, "admin@acme.example.com")
    old_cookie = client.cookies.get("documind_refresh")
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    # Replaying the old (rotated) refresh token revokes every session.
    client.cookies.set("documind_refresh", old_cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth(new_token)).status_code == 401


def test_logout_revokes_access_token(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    assert client.post("/api/v1/auth/logout", headers=auth(token)).status_code == 200
    assert client.get("/api/v1/documents", headers=auth(token)).status_code == 401


def test_tenant_admin_cannot_use_platform_api(client: TestClient, two_tenants: dict) -> None:
    r = client.get("/api/v1/platform/tenants", headers=auth(two_tenants["token_a"]))
    assert r.status_code == 403


def test_read_only_user_cannot_upload_or_delete(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    r = client.post("/api/v1/users", headers=auth(admin), json={
        "email": "reader@acme.example.com", "full_name": "Reader", "password": PASSWORD, "role_codes": ["read_only"]})
    assert r.status_code == 201, r.text
    reader = login(client, "reader@acme.example.com")["access_token"]
    up = client.post("/api/v1/documents", headers=auth(reader), files={"file": ("a.txt", b"hello world", "text/plain")})
    assert up.status_code == 403
    assert up.json()["error"]["code"] == "permission_denied"
    assert client.get("/api/v1/documents", headers=auth(reader)).status_code == 200


def test_privilege_escalation_is_blocked(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    client.post("/api/v1/users", headers=auth(admin), json={
        "email": "dept@acme.example.com", "full_name": "Dept", "password": PASSWORD, "role_codes": ["department_admin"]})
    dept = login(client, "dept@acme.example.com")["access_token"]
    # department admin may create users but may not hand out tenant_admin
    r = client.post("/api/v1/users", headers=auth(dept), json={
        "email": "evil@acme.example.com", "full_name": "Evil", "password": PASSWORD, "role_codes": ["tenant_admin"]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "privilege_escalation"


def test_last_tenant_admin_cannot_be_removed(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    me = client.get("/api/v1/auth/me", headers=auth(admin)).json()
    r = client.patch(f"/api/v1/users/{me['id']}", headers=auth(admin), json={"role_codes": ["standard_user"]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "last_admin"


def test_weak_password_rejected(client: TestClient, two_tenants: dict) -> None:
    r = client.post("/api/v1/users", headers=auth(two_tenants["token_a"]), json={
        "email": "weak@acme.example.com", "full_name": "Weak", "password": "short", "role_codes": ["standard_user"]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "weak_password"


def test_suspended_tenant_blocks_access(client: TestClient, root_token: str, two_tenants: dict) -> None:
    tid = two_tenants["a"]["id"]
    r = client.post(f"/api/v1/platform/tenants/{tid}/status", headers=auth(root_token), json={"status": "suspended"})
    assert r.status_code == 200
    assert client.get("/api/v1/documents", headers=auth(two_tenants["token_a"])).status_code == 403
    r = client.post("/api/v1/auth/login", json={"email": "admin@acme.example.com", "password": PASSWORD})
    assert r.status_code == 403


def test_multi_tenant_user_switches_tenant(client: TestClient, two_tenants: dict) -> None:
    # admin of globex is also invited into acme
    client.post("/api/v1/users", headers=auth(two_tenants["token_a"]), json={
        "email": "admin@globex.example.com", "full_name": "x", "role_codes": ["read_only"]})
    s = login(client, "admin@globex.example.com", tenant_slug="globex")
    assert {t["slug"] for t in s["tenants"]} == {"acme", "globex"}
    r = client.post("/api/v1/auth/switch-tenant", headers=auth(s["access_token"]),
                    json={"tenant_id": two_tenants["a"]["id"]})
    assert r.status_code == 200
    assert r.json()["tenant"]["slug"] == "acme"
    assert "document:create" not in r.json()["permissions"]
