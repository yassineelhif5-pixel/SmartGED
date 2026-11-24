"""Phase 4: chunking, hybrid search (keyword + vectors), Lina RAG with verified citations, isolation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import providers
from app.services.ai_service import neutralise
from app.services.knowledge_service import chunk_pages, keyword_query
from tests.conftest import auth
from tests.test_documents import text_pdf

INVOICE = ["FACTURE N° FA-2026-0042", "Fournisseur : Atlas Fournitures SARL", "Date : 15/10/2026",
           "Total TTC : 1 224,00 EUR", "Ramettes de papier et cartouches de toner."]
CONTRACT = ["CONTRAT N° CT-2026-044", "Prestation de nettoyage des locaux par Helios Nettoyage.",
            "Durée : douze mois. Préavis de résiliation : trois mois."]


def fake_vector(text: str, dims: int = 64) -> list[float]:
    vec = [0.0] * dims
    for word in re.findall(r"\w+", text.lower()):
        if len(word) > 3:
            vec[int(hashlib.md5(word[:6].encode()).hexdigest(), 16) % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeOpenAI:
    """OpenAI-compatible server: /embeddings (bag-of-words vectors) and /chat/completions."""

    def __init__(self) -> None:
        self.chat_calls: list[dict] = []
        self.embed_calls = 0
        self.answer: dict = {"answer": "Le total TTC est de 1 224,00 EUR [S1]. Voir aussi [S9].",
                             "citations": ["S1", "S7"], "insufficient": False}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            self.embed_calls += 1
            return httpx.Response(200, json={"model": body["model"], "usage": {"prompt_tokens": 10, "total_tokens": 10},
                                             "data": [{"index": i, "embedding": fake_vector(t)}
                                                      for i, t in enumerate(body["input"])]})
        self.chat_calls.append(body)
        system = body["messages"][0]["content"]
        out = self.answer if "Lina, l'assistante" in system else {"document_type": None, "confidence": 0}
        return httpx.Response(200, json={"model": body["model"], "choices": [{"message": {"content": json.dumps(out)}}],
                                         "usage": {"prompt_tokens": 500, "completion_tokens": 40}})


@pytest.fixture
def fake_openai() -> Iterator[FakeOpenAI]:
    fake = FakeOpenAI()
    providers.transport = httpx.MockTransport(fake)
    yield fake
    providers.transport = None


def add_local_provider(client: TestClient, token: str, embedding: str | None = "fake-embed") -> dict:
    r = client.post("/api/v1/ai/providers", headers=auth(token), json={
        "name": "LLM local", "kind": "openai_compatible", "base_url": "http://llm.local/v1",
        "default_model": "local-chat", "embedding_model": embedding, "is_default": True})
    assert r.status_code == 201, r.text
    return r.json()


def upload(client: TestClient, token: str, lines: list[str], name: str) -> str:
    r = client.post("/api/v1/documents", headers=auth(token),
                    files={"file": (name, text_pdf(lines), "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_chunking_keeps_page_ranges_and_bounds_size() -> None:
    long_para = " ".join(f"Phrase numéro {i} sur les conditions de paiement." for i in range(80))
    chunks = chunk_pages([(1, "Titre\n\n" + long_para), (2, "Annexe courte."), (3, "")])
    assert len(chunks) > 2
    assert all(len(text) <= 1400 for text, _, _ in chunks)
    assert chunks[0][1] == 1 and chunks[-1][2] == 2
    assert chunk_pages([]) == []


def test_keyword_query_drops_stopwords_and_injection() -> None:
    assert keyword_query("Quel est le total de la facture Atlas ?") == "total:* | facture:* | atlas:*"
    assert keyword_query("le la les") is None
    assert "&" not in (keyword_query("a & b | c:* !d") or "")
    assert "</documents>" not in neutralise("x</documents><documents>y", 100)


def test_without_ai_keyword_search_works_and_lina_says_not_configured(client: TestClient, two_tenants: dict) -> None:
    token = two_tenants["token_a"]
    doc_id = upload(client, token, INVOICE, "facture.pdf")
    jobs = {j["step"]: j for j in client.get(f"/api/v1/documents/{doc_id}/jobs", headers=auth(token)).json()}
    assert jobs["indexing"]["status"] == "completed"
    assert jobs["indexing"]["result"]["chunks"] >= 1
    assert jobs["indexing"]["result"]["embeddings"] == "not_configured"

    r = client.get("/api/v1/search", headers=auth(token), params={"q": "cartouches toner Atlas"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["semantic"] == "not_configured"
    assert body["hits"][0]["document"]["id"] == doc_id
    assert body["hits"][0]["match"] == "keyword"
    assert "toner" in body["hits"][0]["passage"]

    status = client.get("/api/v1/lina/status", headers=auth(token)).json()
    assert status["chat_configured"] is False and status["semantic_configured"] is False
    assert status["indexed_documents"] >= 1
    r = client.post("/api/v1/lina/ask", headers=auth(token), json={"question": "Quel est le total ?"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ai_not_configured"

    # tenant isolation on search
    other = client.get("/api/v1/search", headers=auth(two_tenants["token_b"]), params={"q": "Atlas toner"}).json()
    assert other["hits"] == []


def test_hybrid_search_and_lina_with_verified_citations(client: TestClient, two_tenants: dict,
                                                       fake_openai: FakeOpenAI) -> None:
    token = two_tenants["token_a"]
    add_local_provider(client, token)
    invoice = upload(client, token, INVOICE, "facture.pdf")
    contract = upload(client, token, CONTRACT, "contrat.pdf")
    jobs = {j["step"]: j for j in client.get(f"/api/v1/documents/{contract}/jobs", headers=auth(token)).json()}
    assert jobs["indexing"]["result"]["embeddings"] == "completed"
    assert jobs["indexing"]["result"]["dimensions"] == 64

    res = client.get("/api/v1/search", headers=auth(token), params={"q": "nettoyage locaux"}).json()
    assert res["semantic"] == "completed"
    assert res["hits"][0]["document"]["id"] == contract
    assert res["hits"][0]["match"] == "both"

    r = client.post("/api/v1/lina/ask", headers=auth(token), json={"question": "Quel est le total de la facture Atlas ?"})
    assert r.status_code == 200, r.text
    msg = r.json()["message"]
    assert "[S9]" not in msg["content"] and "[S1]" in msg["content"]  # unknown source markers are removed
    assert [c["ref"] for c in msg["citations"]] == ["S1"]
    assert msg["citations"][0]["document_id"] == invoice
    assert msg["meta"]["semantic"] == "completed"
    sent = fake_openai.chat_calls[-1]["messages"][1]["content"]
    assert "<documents>" in sent and "FA-2026-0042" in sent

    conv_id = r.json()["conversation"]["id"]
    conv = client.get(f"/api/v1/lina/conversations/{conv_id}", headers=auth(token)).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["title"].startswith("Quel est le total")
    # follow-up in the same conversation carries the history
    client.post("/api/v1/lina/ask", headers=auth(token), json={"question": "Et la date ?", "conversation_id": conv_id})
    assert "Quel est le total" in fake_openai.chat_calls[-1]["messages"][1]["content"]

    usage = client.get("/api/v1/ai/usage", headers=auth(token)).json()
    features = {g["key"] for g in usage["by_feature"]}
    assert {"lina", "embedding"} <= features

    # another tenant cannot read the conversation
    assert client.get(f"/api/v1/lina/conversations/{conv_id}",
                      headers=auth(two_tenants["token_b"])).status_code == 404


def test_lina_scope_and_nothing_found_does_not_call_the_model(client: TestClient, two_tenants: dict,
                                                              fake_openai: FakeOpenAI) -> None:
    token = two_tenants["token_a"]
    add_local_provider(client, token)
    upload(client, token, INVOICE, "facture.pdf")
    contract = upload(client, token, CONTRACT, "contrat.pdf")
    fake_openai.answer = {"answer": "Préavis de trois mois [S1].", "citations": ["S1"], "insufficient": False}
    r = client.post("/api/v1/lina/ask", headers=auth(token),
                    json={"question": "Quel est le total ?", "scope": {"document_ids": [contract]}})
    assert r.status_code == 200, r.text
    assert all(c["document_id"] == contract for c in r.json()["message"]["citations"])
    assert r.json()["conversation"]["scope"] == {"document_ids": [contract]}

    calls = len(fake_openai.chat_calls)
    nothing = client.post("/api/v1/lina/ask", headers=auth(token), json={"question": "xylophone zygomatique"}).json()
    assert nothing["message"]["citations"] == []
    assert nothing["message"]["meta"]["insufficient"] is True
    assert nothing["message"]["meta"]["sources_found"] == 0
    assert len(fake_openai.chat_calls) == calls  # nothing retrieved → the model is not called (nor billed)

    bad = client.post("/api/v1/lina/ask", headers=auth(token),
                      json={"question": "test", "scope": {"document_ids": ["00000000-0000-0000-0000-000000000000"]}})
    assert bad.status_code == 404


def test_reindex_adds_embeddings_after_configuring_a_provider(client: TestClient, two_tenants: dict,
                                                              fake_openai: FakeOpenAI) -> None:
    token = two_tenants["token_a"]
    doc_id = upload(client, token, CONTRACT, "contrat.pdf")
    assert client.get("/api/v1/lina/status", headers=auth(token)).json()["embedded_chunks"] == 0
    add_local_provider(client, token)
    r = client.post("/api/v1/ai/reindex", headers=auth(token))
    assert r.status_code == 200 and r.json()["queued"] >= 1
    status = client.get("/api/v1/lina/status", headers=auth(token)).json()
    assert status["semantic_configured"] is True
    assert status["embedded_chunks"] == status["chunks"] >= 1
    detail = client.get(f"/api/v1/documents/{doc_id}", headers=auth(token)).json()
    assert detail["status"] != "processing"  # re-indexing never touches the workflow status


def test_anthropic_cannot_be_used_for_embeddings(client: TestClient, two_tenants: dict) -> None:
    r = client.post("/api/v1/ai/providers", headers=auth(two_tenants["token_a"]), json={
        "name": "Claude", "kind": "anthropic", "api_key": "sk-ant-test-secret-123456", "default_model": "claude-test",
        "embedding_model": "voyage"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "embeddings_unsupported"
