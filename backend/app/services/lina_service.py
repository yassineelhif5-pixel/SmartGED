"""Lina: retrieval-augmented answers over the organisation's documents, with verified citations.

* Retrieval = hybrid search restricted by :func:`knowledge_service.visible_documents` and the
  conversation scope (documents / folder). Lina never sees a passage the user could not open.
* No passage found → an honest "nothing found" answer, without calling (or billing) the model.
* Citations returned by the model are checked against the passages actually provided; unknown
  markers are removed from the answer.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import LinaConversation, LinaMessage
from app.services import ai_service, knowledge_service

MAX_SOURCES = 8
SOURCE_CHARS = 1800
NOTHING_FOUND = ("Je n'ai trouvé aucun passage pertinent dans les documents auxquels vous avez accès pour répondre "
                 "à cette question. Essayez d'autres mots-clés ou élargissez le périmètre.")
_MARK = re.compile(r"\[(S\d{1,2})\]")


def get_conversation(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID) -> LinaConversation:
    conv = db.scalar(select(LinaConversation).where(LinaConversation.id == conversation_id,
                                                    LinaConversation.tenant_id == tenant_id,
                                                    LinaConversation.user_id == user_id))
    if conv is None:
        raise NotFound("Conversation not found")
    return conv


def _history(conv: LinaConversation, turns: int = 4) -> str:
    msgs = conv.messages[-turns * 2:]
    if not msgs:
        return "(aucun)"
    return "\n".join(f"{'Utilisateur' if m.role == 'user' else 'Lina'} : {m.content[:600]}" for m in msgs)


def ask(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, conv: LinaConversation, question: str) -> LinaMessage:
    question = question.strip()
    history = _history(conv)
    user_msg = LinaMessage(tenant_id=tenant_id, conversation_id=conv.id, role="user", content=question,
                           citations=[], meta={})
    db.add(user_msg)
    db.flush()
    key = f"lina:{user_msg.id}"
    retrieval = knowledge_service.retrieve(db, tenant_id, question, limit=MAX_SOURCES, scope=conv.scope,
                                           user_id=user_id, key=key)
    sources: dict[str, dict[str, Any]] = {}
    blocks = []
    for i, hit in enumerate(retrieval.hits, start=1):
        ref = f"S{i}"
        pages = (f"p. {hit.chunk.page_from}" if hit.chunk.page_from == hit.chunk.page_to
                 else f"p. {hit.chunk.page_from}-{hit.chunk.page_to}")
        dtype = hit.document.document_type.name if hit.document.document_type else "non classé"
        sources[ref] = {"ref": ref, "document_id": str(hit.document.id), "title": hit.document.title,
                        "page_from": hit.chunk.page_from, "page_to": hit.chunk.page_to,
                        "excerpt": hit.chunk.text[:400], "match": "+".join(hit.sources)}
        blocks.append(f"[{ref}] « {hit.document.title} » ({dtype}, {pages})\n{hit.chunk.text[:SOURCE_CHARS]}")
    meta: dict[str, Any] = {"semantic": retrieval.semantic, "sources_found": len(sources)}
    if retrieval.detail:
        meta["semantic_detail"] = retrieval.detail[:300]
    if not sources:
        answer, citations = NOTHING_FOUND, []
        meta["insufficient"] = True
    else:
        result = ai_service.run_prompt(
            db, tenant_id, prompt_code="lina_answer", feature="lina", idempotency_key=key, user_id=user_id,
            variables={"question": ai_service.neutralise(question, 2000), "history": ai_service.neutralise(history, 3000),
                       "sources": ai_service.neutralise("\n\n".join(blocks), 30_000), "language": "français"})
        data = result.data or {}
        answer = str(data.get("answer") or result.text or "").strip()
        answer = _MARK.sub(lambda m: m.group(0) if m.group(1) in sources else "", answer)
        cited = [c for c in data.get("citations") or [] if isinstance(c, str) and c in sources]
        cited += [m for m in _MARK.findall(answer) if m in sources and m not in cited]
        citations = [sources[c] for c in dict.fromkeys(cited)]
        meta.update(model=result.completion.model, credits=result.credits, insufficient=bool(data.get("insufficient")),
                    parsed=result.data is not None)
    reply = LinaMessage(tenant_id=tenant_id, conversation_id=conv.id, role="assistant", content=answer or NOTHING_FOUND,
                        citations=citations, meta=meta)
    db.add(reply)
    if conv.title == "Nouvelle conversation":
        conv.title = question[:120]
    conv.updated_at = datetime.now(UTC)
    db.flush()
    return reply


def message_out(m: LinaMessage) -> dict[str, Any]:
    return {"id": str(m.id), "role": m.role, "content": m.content, "citations": m.citations, "meta": m.meta,
            "created_at": m.created_at}


def conversation_out(c: LinaConversation, *, with_messages: bool = False) -> dict[str, Any]:
    out = {"id": str(c.id), "title": c.title, "scope": c.scope, "created_at": c.created_at, "updated_at": c.updated_at}
    if with_messages:
        out["messages"] = [message_out(m) for m in c.messages]
    return out
