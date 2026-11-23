"""Document Splitting Engine: detection, human review, apply (child documents), dismiss, isolation."""

from __future__ import annotations

import io
import json

import httpx
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.ai.splitting import heuristic_segments
from tests.conftest import auth
from tests.test_ai import add_provider, anthropic_reply, fake_ai  # noqa: F401 - fixture

BATCH_PAGES: list[list[str]] = [
    ["FACTURE N° FA-2026-0101", "Fournisseur : Atlas SARL", "Total TTC : 480,00 EUR", "Page 1/2"],
    ["Conditions générales de vente applicables à la commande.", "Pénalités de retard au taux légal.", "Page 2/2"],
    [],  # blank separator sheet
    ["BON DE COMMANDE N° BC-7781", "Client : Globex", "Quantité : 12 cartons de papier A4"],
    ["FACTURE N° FA-2026-0102", "Fournisseur : Orion Services", "Total TTC : 96,00 EUR"],
]


def batch_pdf(pages: list[list[str]] = BATCH_PAGES) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for lines in pages:
        y = 780
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


def upload(client: TestClient, token: str, data: bytes, name: str = "lot.pdf") -> dict:
    r = client.post("/api/v1/documents", headers=auth(token), data={"tags": "scan"},
                    files={"file": (name, data, "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()


def test_heuristic_detects_boundaries_and_keeps_continuations() -> None:
    pages = [(i + 1, "\n".join(lines)) for i, lines in enumerate(BATCH_PAGES)]
    det = heuristic_segments(pages)
    assert [(s["start_page"], s["end_page"]) for s in det.segments] == [(1, 2), (4, 4), (5, 5)]
    assert det.separator_pages == [3]
    assert det.segments[0]["title"] == "Facture FA-2026-0101"
    assert det.confidence is not None and det.confidence >= 0.5


def test_heuristic_does_not_split_a_single_invoice_with_terms_page() -> None:
    pages = [(1, "FACTURE N° FA-2026-0042\nTotal TTC : 1 250,00 EUR\nLa présente facture est payable sous 30 jours."),
             (2, "Page deux : conditions générales de paiement à trente jours.")]
    det = heuristic_segments(pages)
    assert not det.is_multi
    same_ref = [(1, "FACTURE N° FA-9\nPage 1/2"), (2, "FACTURE N° FA-9 (suite)\nPage 2/2")]
    assert not heuristic_segments(same_ref).is_multi


def test_batch_upload_pauses_for_review_then_split_creates_children(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    doc = upload(client, token, batch_pdf())
    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=auth(token)).json()
    assert detail["page_count"] == 5
    assert detail["status"] == "pending_validation"  # waiting for the split review, not published
    jobs = {j["step"]: j for j in client.get(f"/api/v1/documents/{doc['id']}/jobs", headers=auth(token)).json()}
    assert jobs["splitting"]["status"] == "completed"
    assert jobs["splitting"]["result"]["segments"] == 3
    assert jobs["classification"]["status"] == "pending"  # not run on a whole batch

    state = client.get(f"/api/v1/documents/{doc['id']}/split", headers=auth(token)).json()
    assert state["splittable"] is True
    proposal = state["proposal"]
    assert proposal["status"] == "proposed" and proposal["method"] == "heuristic"
    assert proposal["details"]["ai"]["status"] == "not_configured"
    assert len(state["pages"]) == 5

    types = {t["code"]: t for t in client.get("/api/v1/document-types", headers=auth(token)).json()}
    segments = [{"start_page": 1, "end_page": 2, "title": "Facture Atlas", "document_type_id": types["invoice"]["id"]},
                {"start_page": 4, "end_page": 4, "title": "Commande Globex"},
                {"start_page": 5, "end_page": 5}]
    r = client.post(f"/api/v1/documents/{doc['id']}/split/apply", headers=auth(token),
                    json={"segments": segments, "proposal_id": proposal["id"]})
    assert r.status_code == 201, r.text
    out = r.json()
    children = out["children"]
    assert [c["page_count"] for c in children] == [2, 1, 1]
    assert children[0]["title"] == "Facture Atlas"
    assert children[2]["title"].startswith("lot — partie 3")
    assert all(c["parent_document_id"] == doc["id"] for c in children)
    assert out["proposal"]["status"] == "applied"
    assert out["proposal"]["child_document_ids"] == [c["id"] for c in children]

    first = client.get(f"/api/v1/documents/{children[0]['id']}", headers=auth(token)).json()
    assert first["document_type"]["id"] == types["invoice"]["id"]
    assert first["tags"] == ["scan"]
    pages = client.get(f"/api/v1/documents/{children[0]['id']}/pages", headers=auth(token)).json()
    assert [p["page_number"] for p in pages] == [1, 2]
    assert "FA-2026-0101" in pages[0]["text"] and "Conditions" in pages[1]["text"]
    child_jobs = {j["step"]: j for j in client.get(f"/api/v1/documents/{children[1]['id']}/jobs",
                                                   headers=auth(token)).json()}
    assert child_jobs["text_extraction"]["result"]["inherited_from"] == doc["id"]
    assert child_jobs["splitting"]["status"] == "skipped"
    second = client.get(f"/api/v1/documents/{children[1]['id']}", headers=auth(token)).json()
    assert second["status"] in ("published", "pending_validation")

    pdf = client.get(f"/api/v1/documents/{children[0]['id']}/download", headers=auth(token))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    parent = client.get(f"/api/v1/documents/{doc['id']}", headers=auth(token)).json()
    assert parent["status"] == "archived"
    rels = client.get(f"/api/v1/documents/{doc['id']}/relations", headers=auth(token)).json()
    assert {r["document"]["id"] for r in rels if r["relation_type"] == "split_into"} == {c["id"] for c in children}
    assert sum(1 for r in rels if r["relation_type"] == "split_into") == 3

    again = client.post(f"/api/v1/documents/{doc['id']}/split/apply", headers=auth(token),
                        json={"segments": segments})
    assert again.status_code in (409, 422)

    audit = client.get("/api/v1/audit", headers=auth(token), params={"action": "document.split_applied"})
    if audit.status_code == 200:
        assert audit.json()["total"] >= 1


def test_dismiss_resumes_pipeline_as_single_document(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    doc = upload(client, token, batch_pdf())
    r = client.post(f"/api/v1/documents/{doc['id']}/split/dismiss", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["proposal"]["status"] == "dismissed"
    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=auth(token)).json()
    assert detail["status"] == "published"
    jobs = {j["step"]: j for j in client.get(f"/api/v1/documents/{doc['id']}/jobs", headers=auth(token)).json()}
    assert jobs["publication"]["status"] == "completed"
    assert client.post(f"/api/v1/documents/{doc['id']}/split/dismiss", headers=auth(token)).status_code == 404


def test_segments_are_validated(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    doc = upload(client, token, batch_pdf())
    url = f"/api/v1/documents/{doc['id']}/split/apply"
    overlap = [{"start_page": 1, "end_page": 3}, {"start_page": 3, "end_page": 5}]
    assert client.post(url, headers=auth(token), json={"segments": overlap}).status_code == 422
    out_of_range = [{"start_page": 1, "end_page": 2}, {"start_page": 3, "end_page": 9}]
    assert client.post(url, headers=auth(token), json={"segments": out_of_range}).status_code == 422
    whole = [{"start_page": 1, "end_page": 5}]
    assert client.post(url, headers=auth(token), json={"segments": whole}).status_code == 422


def test_single_page_pdf_is_not_splittable(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    doc = upload(client, token, batch_pdf([["FACTURE N° FA-1"]]), "simple.pdf")
    jobs = {j["step"]: j for j in client.get(f"/api/v1/documents/{doc['id']}/jobs", headers=auth(token)).json()}
    assert jobs["splitting"]["status"] == "skipped"
    state = client.get(f"/api/v1/documents/{doc['id']}/split", headers=auth(token)).json()
    assert state["splittable"] is False and state["proposal"] is None
    assert client.post(f"/api/v1/documents/{doc['id']}/split/detect", headers=auth(token)).status_code == 422


def test_split_is_tenant_isolated(client: TestClient, two_tenants: dict) -> None:
    doc = upload(client, two_tenants["token_a"], batch_pdf())
    tb = two_tenants["token_b"]
    assert client.get(f"/api/v1/documents/{doc['id']}/split", headers=auth(tb)).status_code == 404
    assert client.post(f"/api/v1/documents/{doc['id']}/split/apply", headers=auth(tb),
                       json={"segments": [{"start_page": 1, "end_page": 2}]}).status_code == 404
    assert client.get(f"/api/v1/documents/{doc['id']}/pages/1/thumbnail", headers=auth(tb)).status_code == 404


def test_page_thumbnail_is_png(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    doc = upload(client, token, batch_pdf())
    r = client.get(f"/api/v1/documents/{doc['id']}/pages/4/thumbnail?width=160", headers=auth(token))
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")
    assert client.get(f"/api/v1/documents/{doc['id']}/pages/9/thumbnail", headers=auth(token)).status_code == 404


def test_ai_detection_is_validated_and_typed(client: TestClient, two_tenants: dict, fake_ai) -> None:  # noqa: F811
    token = two_tenants["token_a"]
    add_provider(client, token)

    def splitting(request: httpx.Request) -> httpx.Response | None:
        body = json.loads(request.content)
        if "frontières" not in body.get("system", ""):
            return None
        return anthropic_reply({"documents": [
            {"start_page": 1, "end_page": 2, "document_type": "invoice", "title": "Facture Atlas", "confidence": 0.9,
             "reason": "en-tête facture"},
            {"start_page": 4, "end_page": 4, "document_type": "unknown_code", "title": None, "confidence": 0.8},
            {"start_page": 5, "end_page": 5, "document_type": "invoice", "title": "Facture Orion", "confidence": 0.85},
        ]})

    fake_ai.override = splitting
    doc = upload(client, token, batch_pdf())
    state = client.get(f"/api/v1/documents/{doc['id']}/split", headers=auth(token)).json()
    proposal = state["proposal"]
    assert proposal["method"] == "ai"
    assert proposal["separator_pages"] == [3]
    segs = proposal["segments"]
    assert segs[0]["document_type_code"] == "invoice" and segs[0]["document_type_id"]
    assert segs[1]["document_type_code"] is None  # unknown code from the model is never trusted
    assert "confirmed_by_heuristic" in segs[2]["reasons"]

    # An invalid AI answer (overlap) falls back to the heuristic, and says so.
    def broken(request: httpx.Request) -> httpx.Response | None:
        body = json.loads(request.content)
        if "frontières" not in body.get("system", ""):
            return None
        return anthropic_reply({"documents": [{"start_page": 1, "end_page": 3}, {"start_page": 2, "end_page": 5}]})

    fake_ai.override = broken
    r = client.post(f"/api/v1/documents/{doc['id']}/split/detect", headers=auth(token))
    assert r.status_code == 200, r.text
    p2 = r.json()["proposal"]
    assert p2["method"] == "heuristic" and "invalid AI answer" in p2["details"]["ai"]["error"]
