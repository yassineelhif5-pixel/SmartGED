"""Phase 4 API: hybrid search, Lina (RAG assistant with citations) and knowledge re-indexing."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import AIProviderError
from app.core.errors import Conflict, ValidationFailed
from app.database.session import get_db
from app.models import Document, Folder, LinaConversation
from app.repositories.base import get_owned
from app.schemas.common import Message
from app.schemas.ged import DocumentOut
from app.security.context import Principal, require
from app.services import ai_service, knowledge_service, lina_service
from app.workers.celery_app import enqueue_indexing

router = APIRouter(tags=["Search & Lina"])


class SearchHit(BaseModel):
    document: DocumentOut
    score: float
    match: str  # keyword | semantic | both
    passage: str | None
    page_from: int | None
    page_to: int | None
    similarity: float | None


class SearchResponse(BaseModel):
    query: str
    semantic: str
    semantic_detail: str | None
    hits: list[SearchHit]


class Scope(BaseModel):
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    folder_id: uuid.UUID | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: uuid.UUID | None = None
    scope: Scope | None = None


class LinaStatus(BaseModel):
    chat_configured: bool
    semantic_configured: bool
    chunks: int
    embedded_chunks: int
    indexed_documents: int
    embedding_provider: str | None
    embedding_model: str | None


@router.get("/search", response_model=SearchResponse)
def hybrid_search(q: str = Query(min_length=2, max_length=300), limit: int = Query(20, ge=1, le=50),
                  p: Principal = Depends(require("document:read")), db: Session = Depends(get_db)) -> SearchResponse:
    results, retrieval = knowledge_service.search_documents(db, p.tenant_id, q, limit=limit, user_id=p.user.id,
                                                            key=f"search:{uuid.uuid4()}")
    db.commit()  # usage ledger for the query embedding
    return SearchResponse(query=q, semantic=retrieval.semantic, semantic_detail=retrieval.detail, hits=[
        SearchHit(document=DocumentOut.model_validate(r["document"]), score=r["score"], match=r["match"],
                  passage=(r["passage"] or None) and r["passage"][:500], page_from=r["page_from"],
                  page_to=r["page_to"], similarity=r["similarity"]) for r in results])


@router.get("/lina/status", response_model=LinaStatus)
def lina_status(p: Principal = Depends(require("ai_assistant:read")), db: Session = Depends(get_db)) -> LinaStatus:
    s = knowledge_service.stats(db, p.tenant_id)
    return LinaStatus(chat_configured=ai_service.active_provider(db, p.tenant_id) is not None,
                      semantic_configured=s["embedding_model"] is not None, **s)


@router.get("/lina/conversations")
def list_conversations(p: Principal = Depends(require("ai_assistant:read")),
                       db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(LinaConversation).where(LinaConversation.tenant_id == p.tenant_id,
                                                     LinaConversation.user_id == p.user.id)
                      .order_by(LinaConversation.updated_at.desc()).limit(100))
    return [lina_service.conversation_out(c) for c in rows]


@router.get("/lina/conversations/{conversation_id}")
def get_conversation(conversation_id: uuid.UUID, p: Principal = Depends(require("ai_assistant:read")),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
    conv = lina_service.get_conversation(db, p.tenant_id, p.user.id, conversation_id)
    return lina_service.conversation_out(conv, with_messages=True)


@router.delete("/lina/conversations/{conversation_id}", response_model=Message)
def delete_conversation(conversation_id: uuid.UUID, p: Principal = Depends(require("ai_assistant:read")),
                        db: Session = Depends(get_db)) -> Message:
    db.delete(lina_service.get_conversation(db, p.tenant_id, p.user.id, conversation_id))
    db.commit()
    return Message(message="Conversation deleted")


@router.post("/lina/ask")
def ask(body: AskIn, p: Principal = Depends(require("ai_assistant:read", "document:read")),
        db: Session = Depends(get_db)) -> dict[str, Any]:
    if ai_service.active_provider(db, p.tenant_id) is None:
        raise Conflict("Lina needs an AI provider: configure one in Administration → Intelligence IA",
                       code="ai_not_configured")
    if body.conversation_id:
        conv = lina_service.get_conversation(db, p.tenant_id, p.user.id, body.conversation_id)
    else:
        scope: dict[str, Any] = {}
        if body.scope:
            for doc_id in body.scope.document_ids:
                get_owned(db, Document, p.tenant_id, doc_id, label="Document")
            if body.scope.folder_id:
                get_owned(db, Folder, p.tenant_id, body.scope.folder_id, label="Folder")
            scope = {k: v for k, v in body.scope.model_dump(mode="json").items() if v}
        conv = LinaConversation(tenant_id=p.tenant_id, user_id=p.user.id, title="Nouvelle conversation", scope=scope)
        db.add(conv)
        db.flush()
    from app.core.errors import QuotaExceeded
    from app.services.ai_service import AINotConfigured

    try:
        reply = lina_service.ask(db, p.tenant_id, p.user.id, conv, body.question)
    except AINotConfigured as exc:
        raise Conflict(str(exc), code="ai_not_configured") from exc
    except QuotaExceeded:
        db.commit()
        raise
    except AIProviderError as exc:
        db.commit()  # keep the question and the usage ledger
        raise ValidationFailed(f"The AI provider did not answer: {exc}", code="ai_provider_error") from exc
    p.audit(db, "lina.asked", resource_type="lina_conversation", resource_id=conv.id,
            details={"sources": len(reply.citations), "semantic": reply.meta.get("semantic")})
    db.commit()
    db.refresh(conv)
    return {"conversation": lina_service.conversation_out(conv), "message": lina_service.message_out(reply)}


class ReindexResult(BaseModel):
    queued: int
    started_at: datetime


@router.post("/ai/reindex", response_model=ReindexResult)
def reindex(p: Principal = Depends(require("processing:administer")), db: Session = Depends(get_db)) -> ReindexResult:
    ids = list(db.scalars(select(Document.id).where(Document.tenant_id == p.tenant_id, Document.deleted_at.is_(None))))
    p.audit(db, "knowledge.reindex_requested", resource_type="tenant", resource_id=p.tenant_id,
            details={"documents": len(ids)})
    db.commit()
    for doc_id in ids:
        enqueue_indexing(p.tenant_id, doc_id)
    return ReindexResult(queued=len(ids), started_at=datetime.now())
