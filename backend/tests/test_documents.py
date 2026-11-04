"""Core ECM flows: upload → real OCR pipeline → metadata → validation → versions → trash."""

import io

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from tests.conftest import PASSWORD, auth, login


def text_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 780
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.drawString(72, 780, "Page deux : conditions générales de paiement à trente jours.")
    c.save()
    return buf.getvalue()


def scanned_png(text: str) -> bytes:
    img = Image.new("L", (1600, 400), 255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 64)
    except OSError:
        font = ImageFont.load_default(size=64)
    draw.text((60, 150), text, fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


INVOICE_LINES = [
    "FACTURE N° FA-2026-0042", "Fournisseur : Société Atlas SARL", "Date : 15/10/2026",
    "Total TTC : 1 250,00 EUR", "La présente facture est payable dans les trente jours pour la prestation.",
]


def _types(client: TestClient, token: str) -> dict:
    return {t["code"]: t for t in client.get("/api/v1/document-types", headers=auth(token)).json()}


def test_pdf_upload_runs_real_pipeline_and_is_searchable(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    r = client.post("/api/v1/documents", headers=auth(token), data={"tags": "Finance, urgent"},
                    files={"file": ("facture.pdf", text_pdf(INVOICE_LINES), "application/pdf")})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    doc = client.get(f"/api/v1/documents/{doc_id}", headers=auth(token)).json()
    assert doc["ocr_status"] == "completed"
    assert doc["page_count"] == 2
    assert doc["language"] == "fr"
    assert doc["tags"] == ["finance", "urgent"]
    assert doc["scan_status"] == "not_configured"  # never claimed clean without an antivirus
    assert doc["ai_status"] == "not_configured"  # no AI provider → honest state, nothing simulated
    assert doc["status"] == "published"
    pages = client.get(f"/api/v1/documents/{doc_id}/pages", headers=auth(token)).json()
    assert pages[0]["method"] == "text_layer" and "FA-2026-0042" in pages[0]["text"]
    jobs = {j["step"]: j["status"] for j in client.get(f"/api/v1/documents/{doc_id}/jobs", headers=auth(token)).json()}
    assert jobs["text_extraction"] == "completed" and jobs["classification"] == "not_configured"

    hits = client.get("/api/v1/documents", params={"q": "Atlas", "sort": "relevance"}, headers=auth(token)).json()
    assert hits["total"] == 1 and hits["items"][0]["id"] == doc_id
    assert client.get("/api/v1/documents", params={"q": "inexistant"}, headers=auth(token)).json()["total"] == 0
    assert client.get("/api/v1/documents", params={"tag": "finance"}, headers=auth(token)).json()["total"] == 1


def test_scanned_image_is_ocrd_with_tesseract(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    r = client.post("/api/v1/documents", headers=auth(token),
                    files={"file": ("scan.png", scanned_png("INVOICE 98765 PAID"), "image/png")})
    doc_id = r.json()["id"]
    pages = client.get(f"/api/v1/documents/{doc_id}/pages", headers=auth(token)).json()
    assert pages[0]["method"] == "tesseract"
    assert "98765" in pages[0]["text"]
    assert pages[0]["confidence"] > 0.5


def test_upload_rejects_spoofed_and_disallowed_files(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    r = client.post("/api/v1/documents", headers=auth(token), files={"file": ("x.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_type"
    r = client.post("/api/v1/documents", headers=auth(token), files={"file": ("run.exe", b"MZ\x90\x00", "application/octet-stream")})
    assert r.json()["error"]["code"] == "extension_not_allowed"
    r = client.post("/api/v1/documents", headers=auth(token), files={"file": ("img.png", b"%PDF-1.4 fake", "image/png")})
    assert r.json()["error"]["code"] == "mime_mismatch"
    r = client.post("/api/v1/documents", headers=auth(token), files={"file": ("x.txt", b"", "text/plain")})
    assert r.json()["error"]["code"] == "empty_file"


def test_duplicate_detection(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    first = client.post("/api/v1/documents", headers=auth(token), files={"file": ("a.txt", b"same content here", "text/plain")}).json()
    second = client.post("/api/v1/documents", headers=auth(token), files={"file": ("b.txt", b"same content here", "text/plain")}).json()
    assert second["duplicate_of_id"] == first["id"]
    # same bytes in another tenant are NOT reported as duplicates (no cross-tenant leak)
    other = client.post("/api/v1/documents", headers=auth(two_tenants["token_b"]),
                        files={"file": ("a.txt", b"same content here", "text/plain")}).json()
    assert other["duplicate_of_id"] is None


def test_metadata_validation_workflow(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    invoice = _types(client, token)["invoice"]
    doc = client.post("/api/v1/documents", headers=auth(token), data={"document_type_id": invoice["id"]},
                      files={"file": ("f.pdf", text_pdf(INVOICE_LINES), "application/pdf")}).json()
    assert doc["status"] == "pending_validation"
    url = f"/api/v1/documents/{doc['id']}/metadata"
    bad = client.put(url, headers=auth(token), json={"values": {"invoice_date": "not a date", "total_amount": "abc"}})
    assert bad.status_code == 422 and len(bad.json()["error"]["details"]) == 2
    unknown = client.put(url, headers=auth(token), json={"values": {"hacker_field": 1}})
    assert unknown.status_code == 422
    values = {"invoice_number": "FA-2026-0042", "invoice_date": "15/10/2026", "supplier_name": "Atlas SARL",
              "total_amount": "1 250,00"}
    ok = client.put(url, headers=auth(token), json={"values": values}).json()
    by_name = {m["technical_name"]: m for m in ok["metadata"]}
    assert by_name["invoice_date"]["value"] == "2026-10-15"
    assert by_name["total_amount"]["value"] == "1250.00"
    assert ok["status"] == "pending_validation"
    empty_required = client.put(url, headers=auth(token), json={"values": {"supplier_name": ""}})
    assert empty_required.status_code == 422  # required field cannot be cleared
    required = [m["technical_name"] for m in ok["metadata"] if m["required"] or m["data_type"] in ("currency", "decimal")]
    client.put(url, headers=auth(token), json={"values": {"vat_amount": "208.33"}})
    final = client.put(url, headers=auth(token), json={"values": {}, "validate_fields": required}).json()
    assert final["status"] == "published" and final["validation_status"] == "completed"
    # a standard user cannot validate
    client.post("/api/v1/users", headers=auth(token), json={"email": "u@acme.example.com", "full_name": "U",
                                                              "password": PASSWORD, "role_codes": ["standard_user"]})
    user = login(client, "u@acme.example.com")["access_token"]
    r = client.put(url, headers=auth(user), json={"values": {}, "validate_fields": ["invoice_number"]})
    assert r.status_code == 403


def test_versions_checkout_and_download(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    doc = client.post("/api/v1/documents", headers=auth(token), files={"file": ("n.txt", b"version one text", "text/plain")}).json()
    base = f"/api/v1/documents/{doc['id']}"
    client.post("/api/v1/users", headers=auth(token), json={"email": "w@acme.example.com", "full_name": "W",
                                                            "password": PASSWORD, "role_codes": ["standard_user"]})
    other = login(client, "w@acme.example.com")["access_token"]
    assert client.post(f"{base}/checkout", headers=auth(token)).json()["checked_out_by"] is not None
    blocked = client.post(f"{base}/versions", headers=auth(other), files={"file": ("n.txt", b"other edit", "text/plain")})
    assert blocked.status_code == 409
    v2 = client.post(f"{base}/versions", headers=auth(token), data={"comment": "typo fix"},
                     files={"file": ("n.txt", b"version two text", "text/plain")})
    assert v2.status_code == 201 and v2.json()["current_version"] == 2
    client.post(f"{base}/checkin", headers=auth(token))
    versions = client.get(f"{base}/versions", headers=auth(token)).json()
    assert [v["version_number"] for v in versions] == [2, 1]
    assert client.get(f"{base}/download", headers=auth(token)).content == b"version two text"
    assert client.get(f"{base}/download", params={"version": 1}, headers=auth(token)).content == b"version one text"
    assert client.get(f"{base}/pages", headers=auth(token)).json()[0]["text"] == "version two text"


def test_trash_restore_purge_and_folders(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    parent = client.post("/api/v1/folders", headers=auth(token), json={"name": "Projets"}).json()
    child = client.post("/api/v1/folders", headers=auth(token), json={"name": "2026", "parent_id": parent["id"]}).json()
    dup = client.post("/api/v1/folders", headers=auth(token), json={"name": "projets"})
    assert dup.status_code == 409
    cycle = client.patch(f"/api/v1/folders/{parent['id']}", headers=auth(token), json={"parent_id": child["id"]})
    assert cycle.status_code == 422
    doc = client.post("/api/v1/documents", headers=auth(token), data={"folder_id": child["id"]},
                      files={"file": ("p.txt", b"project plan document", "text/plain")}).json()
    rec = client.get("/api/v1/documents", params={"folder_id": parent["id"], "recursive": True}, headers=auth(token)).json()
    assert rec["total"] == 1
    assert client.delete(f"/api/v1/folders/{parent['id']}", headers=auth(token)).status_code == 200
    trash = client.get("/api/v1/documents", params={"trashed": True}, headers=auth(token)).json()
    assert trash["items"][0]["id"] == doc["id"]
    restored = client.post(f"/api/v1/documents/{doc['id']}/restore", headers=auth(token)).json()
    assert restored["deleted_at"] is None and restored["folder_id"] is None  # folder gone → back to root
    assert client.delete(f"/api/v1/documents/{doc['id']}/purge", headers=auth(token)).status_code == 422
    client.delete(f"/api/v1/documents/{doc['id']}", headers=auth(token))
    assert client.delete(f"/api/v1/documents/{doc['id']}/purge", headers=auth(token)).status_code == 200
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=auth(token)).status_code == 404


def test_document_type_designer_versions_schema(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    body = {"code": "payslip", "name": "Bulletin de salaire", "fields": [
        {"technical_name": "employee", "display_name": "Salarié", "data_type": "text", "required": True},
        {"technical_name": "period", "display_name": "Période", "data_type": "dropdown",
         "allowed_values": ["T1", "T2"]},
    ]}
    created = client.post("/api/v1/document-types", headers=auth(token), json=body)
    assert created.status_code == 201
    dt = created.json()
    assert dt["schema_version"] == 1
    body["fields"] = [dict(f, id=dt["fields"][i]["id"]) for i, f in enumerate(body["fields"])]
    body["fields"].append({"technical_name": "net_pay", "display_name": "Net à payer", "data_type": "currency"})
    updated = client.put(f"/api/v1/document-types/{dt['id']}", headers=auth(token), json=body).json()
    assert updated["schema_version"] == 2 and len(updated["fields"]) == 3
    bad = dict(body, code="payslip2", fields=[{"technical_name": "x", "display_name": "x", "data_type": "dropdown"}])
    assert client.post("/api/v1/document-types", headers=auth(token), json=bad).status_code == 422


def test_dashboard_uses_real_data(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    empty = client.get("/api/v1/dashboard", headers=auth(token)).json()
    assert empty["documents_total"] == 0
    client.post("/api/v1/documents", headers=auth(token), files={"file": ("a.txt", b"dashboard test data", "text/plain")})
    stats = client.get("/api/v1/dashboard", headers=auth(token)).json()
    assert stats["documents_total"] == 1 and stats["uploads_last_30_days"][-1]["uploads"] == 1
    assert stats["storage_bytes"] == len(b"dashboard test data")
