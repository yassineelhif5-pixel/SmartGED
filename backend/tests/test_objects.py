"""Business objects: non-document elements that feed documents."""

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, auth, login


def _types(client: TestClient, token: str, path: str) -> dict:
    return {t["code"]: t for t in client.get(f"/api/v1/{path}", headers=auth(token)).json()}


def _supplier(client: TestClient, token: str) -> dict:
    otype = _types(client, token, "object-types")["supplier"]
    r = client.post("/api/v1/objects", headers=auth(token), json={
        "object_type_id": otype["id"], "code": "FRN-001", "name": "Atlas Fournitures SARL",
        "attributes": {"supplier_vat": "FR12345678901", "payment_terms_days": "30", "email": "compta@atlas.fr"}})
    assert r.status_code == 201, r.text
    return r.json()


def test_starter_object_types_and_crud(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    assert {"supplier", "customer", "project"} <= set(_types(client, token, "object-types"))
    obj = _supplier(client, token)
    assert obj["attributes"]["payment_terms_days"] == 30  # coerced with the type's field definitions
    otype_id = obj["object_type"]["id"]
    dup = client.post("/api/v1/objects", headers=auth(token),
                      json={"object_type_id": otype_id, "code": "FRN-001", "name": "Autre"})
    assert dup.status_code == 409
    bad = client.post("/api/v1/objects", headers=auth(token),
                      json={"object_type_id": otype_id, "code": "X", "name": "X", "attributes": {"nope": 1}})
    assert bad.status_code == 422
    found = client.get("/api/v1/objects", params={"q": "atlas", "type_code": "supplier"}, headers=auth(token)).json()
    assert found["total"] == 1
    # isolation: other tenant sees nothing and cannot read by id
    tb = two_tenants["token_b"]
    assert client.get("/api/v1/objects", params={"q": "atlas"}, headers=auth(tb)).json()["total"] == 0
    assert client.get(f"/api/v1/objects/{obj['id']}", headers=auth(tb)).status_code == 404


def test_reference_field_links_and_autofills_invoice(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    supplier = _supplier(client, token)
    invoice = _types(client, token, "document-types")["invoice"]
    doc = client.post("/api/v1/documents", headers=auth(token), data={"document_type_id": invoice["id"]},
                      files={"file": ("f.txt", b"facture atlas 42", "text/plain")}).json()
    url = f"/api/v1/documents/{doc['id']}/metadata"
    r = client.put(url, headers=auth(token), json={"values": {"supplier_ref": supplier["id"], "invoice_number": "FA-42"}})
    assert r.status_code == 200, r.text
    meta = {m["technical_name"]: m for m in r.json()["metadata"]}
    assert meta["supplier_ref"]["display_value"] == "FRN-001 — Atlas Fournitures SARL"
    assert meta["supplier_name"]["value"] == "Atlas Fournitures SARL" and meta["supplier_name"]["source"] == "object"
    assert meta["supplier_vat"]["value"] == "FR12345678901"
    assert meta["invoice_number"]["value"] == "FA-42" and meta["invoice_number"]["source"] == "manual"

    links = client.get(f"/api/v1/documents/{doc['id']}/objects", headers=auth(token)).json()
    assert {lk["role"] for lk in links} >= {"supplier_ref"}
    by_object = client.get("/api/v1/documents", params={"object_id": supplier["id"]}, headers=auth(token)).json()
    assert by_object["total"] == 1

    # a random uuid or an object of another type is refused
    project = _types(client, token, "object-types")["project"]
    proj = client.post("/api/v1/objects", headers=auth(token),
                       json={"object_type_id": project["id"], "code": "P1", "name": "Projet 1"}).json()
    r = client.put(url, headers=auth(token), json={"values": {"supplier_ref": proj["id"]}})
    assert r.status_code == 422


def test_manual_apply_link_unlink_and_archive(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    supplier = _supplier(client, token)
    invoice = _types(client, token, "document-types")["invoice"]
    doc = client.post("/api/v1/documents", headers=auth(token), data={"document_type_id": invoice["id"]},
                      files={"file": ("g.txt", b"another invoice", "text/plain")}).json()
    client.put(f"/api/v1/documents/{doc['id']}/metadata", headers=auth(token),
               json={"values": {"supplier_name": "Saisie manuelle"}})
    res = client.post(f"/api/v1/documents/{doc['id']}/apply-object", headers=auth(token),
                      json={"object_id": supplier["id"]}).json()
    assert "supplier_vat" in res["filled"] and "supplier_name" in res["skipped"]  # never overwrites by default
    res = client.post(f"/api/v1/documents/{doc['id']}/apply-object", headers=auth(token),
                      json={"object_id": supplier["id"], "overwrite": True}).json()
    assert "supplier_name" in res["filled"]
    links = client.get(f"/api/v1/documents/{doc['id']}/objects", headers=auth(token)).json()
    assert len(links) == 1 and links[0]["role"] == "source"
    # deleting an object still referenced archives it
    msg = client.delete(f"/api/v1/objects/{supplier['id']}", headers=auth(token)).json()["message"]
    assert "archived" in msg
    assert client.get(f"/api/v1/objects/{supplier['id']}", headers=auth(token)).json()["status"] == "archived"
    client.delete(f"/api/v1/documents/{doc['id']}/objects/{links[0]['id']}", headers=auth(token))
    assert client.get(f"/api/v1/documents/{doc['id']}/objects", headers=auth(token)).json() == []


def test_read_only_user_cannot_create_objects(client: TestClient, two_tenants: dict) -> None:
    admin = two_tenants["token_a"]
    client.post("/api/v1/users", headers=auth(admin), json={
        "email": "ro@acme.example.com", "full_name": "RO", "password": PASSWORD, "role_codes": ["read_only"]})
    ro = login(client, "ro@acme.example.com")["access_token"]
    otype = _types(client, admin, "object-types")["supplier"]
    assert client.get("/api/v1/objects", headers=auth(ro)).status_code == 200
    r = client.post("/api/v1/objects", headers=auth(ro), json={"object_type_id": otype["id"], "code": "A", "name": "A"})
    assert r.status_code == 403


def test_object_type_designer(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    body = {"code": "vehicle", "name": "Véhicule", "fields": [
        {"technical_name": "plate", "display_name": "Immatriculation", "data_type": "text", "required": True}]}
    t = client.post("/api/v1/object-types", headers=auth(token), json=body)
    assert t.status_code == 201
    body["fields"][0]["id"] = t.json()["fields"][0]["id"]
    body["fields"].append({"technical_name": "km", "display_name": "Kilométrage", "data_type": "integer"})
    up = client.put(f"/api/v1/object-types/{t.json()['id']}", headers=auth(token), json=body).json()
    assert up["schema_version"] == 2 and len(up["fields"]) == 2
    missing = client.post("/api/v1/objects", headers=auth(token),
                          json={"object_type_id": up["id"], "code": "V1", "name": "Clio"})
    assert missing.status_code == 422  # required attribute
    # a document type can reference the new object type, not an unknown one
    dt = {"code": "fleet_doc", "name": "Carte grise", "fields": [
        {"technical_name": "vehicle_ref", "display_name": "Véhicule", "data_type": "reference",
         "validation_rules": {"object_type_code": "vehicle"}}]}
    assert client.post("/api/v1/document-types", headers=auth(token), json=dt).status_code == 201
    dt["code"] = "bad"
    dt["fields"][0]["validation_rules"] = {"object_type_code": "unicorn"}
    assert client.post("/api/v1/document-types", headers=auth(token), json=dt).status_code == 422
