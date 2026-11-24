"""Phase 4 knowledge layer: chunking, embeddings, hybrid retrieval (full-text + vector, RRF fusion).

* Chunks are built from the OCR pages and always stored: keyword retrieval works without any AI.
* Embeddings are computed only with an active provider that has an ``embedding_model``; otherwise
  semantic search is reported as ``not_configured`` (never simulated).
* Every retrieval goes through :func:`visible_documents` — the single place where document-level
  access rules apply (tenant, trash, split parents today; folder / document ACLs plug in here).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, delete, exists, func, literal_column, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from app.ai.providers import AIProviderError, Completion, embed
from app.core.errors import QuotaExceeded
from app.core.logging import get_logger
from app.models import AIProvider, Document, DocumentChunk, DocumentStatus, Folder, OcrPage

log = get_logger(__name__)

CHUNK_TARGET = 1200
CHUNK_OVERLAP = 150
EMBED_BATCH = 32
RRF_K = 60
STOPWORDS = set("""
le la les un une des du de d l au aux et ou en dans sur pour par avec sans ce cet cette ces qui que quoi
quel quelle quels quelles est sont été être avoir a ont il elle ils elles on nous vous je tu me te se
son sa ses leur leurs mon ma mes ton ta tes notre votre nos vos y ne pas plus moins tout tous toute
toutes comment combien quand où pourquoi the of and or to in on for with is are was what which who how
""".split())


# ------------------------------------------------------------------ chunking
def chunk_pages(pages: list[tuple[int, str]], target: int = CHUNK_TARGET,
                overlap: int = CHUNK_OVERLAP) -> list[tuple[str, int, int]]:
    """Split page texts into ~target-char chunks on paragraph/sentence boundaries, keeping page ranges."""
    pieces: list[tuple[int, str]] = []
    for number, text in pages:
        for para in re.split(r"\n\s*\n|\n(?=[A-ZÀ-Ý0-9])", text or ""):
            para = " ".join(para.split())
            if not para:
                continue
            while len(para) > target:
                cut = para.rfind(". ", 0, target)
                cut = cut + 1 if cut > target // 2 else target
                pieces.append((number, para[:cut].strip()))
                para = para[cut:].strip()
            if para:
                pieces.append((number, para))
    chunks: list[tuple[str, int, int]] = []
    buf: list[str] = []
    first = last = None
    size = 0
    for number, piece in pieces:
        if buf and size + len(piece) + 1 > target:
            chunks.append(("\n".join(buf), first or number, last or number))
            tail = "\n".join(buf)[-overlap:] if overlap else ""
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            buf, size, first = ([tail] if tail else []), len(tail), last
        if first is None:
            first = number
        buf.append(piece)
        size += len(piece) + 1
        last = number
    if buf:
        chunks.append(("\n".join(buf), first or 1, last or first or 1))
    return chunks


# --------------------------------------------------------------- embeddings
def embedding_provider(db: Session, tenant_id: uuid.UUID) -> AIProvider | None:
    return db.scalar(select(AIProvider).where(
        AIProvider.tenant_id == tenant_id, AIProvider.is_active.is_(True), AIProvider.embedding_model.is_not(None),
        AIProvider.embedding_model != "").order_by(AIProvider.is_default.desc(), AIProvider.created_at).limit(1))


def _embed(db: Session, tenant_id: uuid.UUID, provider: AIProvider, texts: list[str], *, key: str,
           document_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> list[list[float]]:
    from app.services.ai_service import check_quota, provider_config, record_usage

    check_quota(db, tenant_id)
    model = provider.embedding_model or ""
    try:
        result = embed(provider_config(provider, model), texts)
    except AIProviderError as exc:
        record_usage(db, tenant_id=tenant_id, key=key, feature="embedding", provider=provider, model=model,
                     prompt=None, document_id=document_id, user_id=user_id, completion=None, error=str(exc))
        raise
    record_usage(db, tenant_id=tenant_id, key=key, feature="embedding", provider=provider, model=model, prompt=None,
                 document_id=document_id, user_id=user_id, error=None,
                 completion=Completion(text="", input_tokens=result.input_tokens, output_tokens=0,
                                       latency_ms=result.latency_ms, model=model))
    return result.vectors


def index_document(db: Session, doc: Document, *, key: str) -> dict[str, Any]:
    """(Re)build the document's chunks for its current version, with embeddings when configured."""
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    pages = [(n, t or "") for n, t in db.execute(select(OcrPage.page_number, OcrPage.text).where(
        OcrPage.document_id == doc.id, OcrPage.version_number == doc.current_version).order_by(OcrPage.page_number))]
    if not pages and doc.content_text:
        pages = [(1, doc.content_text)]
    rows = [DocumentChunk(tenant_id=doc.tenant_id, document_id=doc.id, version_number=doc.current_version,
                          chunk_index=i, page_from=a, page_to=b, text=text, char_count=len(text))
            for i, (text, a, b) in enumerate(chunk_pages(pages))]
    db.add_all(rows)
    db.flush()
    out: dict[str, Any] = {"full_text": True, "chunks": len(rows)}
    if not rows:
        out["embeddings"] = "no_text"
        return out
    provider = embedding_provider(db, doc.tenant_id)
    if provider is None:
        out["embeddings"] = "not_configured"
        return out
    try:
        for start in range(0, len(rows), EMBED_BATCH):
            batch = rows[start:start + EMBED_BATCH]
            vectors = _embed(db, doc.tenant_id, provider, [r.text for r in batch], document_id=doc.id,
                             key=f"{key}:emb{start}")
            for row, vec in zip(batch, vectors, strict=True):
                row.embedding = vec
                row.embedding_model = provider.embedding_model
        db.flush()
        out.update(embeddings="completed", model=provider.embedding_model, dimensions=len(rows[0].embedding or []))
    except QuotaExceeded as exc:
        out.update(embeddings="skipped", reason=exc.message)
    except AIProviderError as exc:
        log.warning("embedding_failed", extra={"document_id": str(doc.id), "error": str(exc)})
        out.update(embeddings="failed", reason=str(exc)[:500])
    return out


# ---------------------------------------------------------------- retrieval
def visible_documents(tenant_id: uuid.UUID, scope: dict[str, Any] | None = None) -> ColumnElement[bool]:
    """Documents a member may retrieve from. Single place for document-level access rules."""
    child = aliased(Document)
    cond = and_(
        Document.tenant_id == tenant_id,
        Document.deleted_at.is_(None),
        Document.status != DocumentStatus.rejected,
        # a split batch is replaced by its child documents
        ~and_(Document.status == DocumentStatus.archived,
              exists().where(child.parent_document_id == Document.id, child.deleted_at.is_(None))),
    )
    scope = scope or {}
    if scope.get("document_ids"):
        cond = and_(cond, Document.id.in_([uuid.UUID(str(d)) for d in scope["document_ids"]]))
    if scope.get("folder_id"):
        folder_id = uuid.UUID(str(scope["folder_id"]))
        tree = select(Folder.id).where(Folder.id == folder_id, Folder.tenant_id == tenant_id).cte(recursive=True)
        tree = tree.union_all(select(Folder.id).where(Folder.parent_id == tree.c.id, Folder.deleted_at.is_(None)))
        cond = and_(cond, Document.folder_id.in_(select(tree.c.id)))
    return cond


def keyword_query(text: str) -> str | None:
    """OR-query over significant words (natural-language questions rarely match with AND)."""
    words = [w for w in re.findall(r"[\wÀ-ÿ'-]+", text.lower()) if len(w) > 1]
    words = [w.strip("'-") for w in words if w.strip("'-") not in STOPWORDS]
    words = [re.sub(r"[^\w]", "", w) for w in words]
    words = list(dict.fromkeys(w for w in words if w))[:16]
    if not words:
        return None
    return " | ".join(f"{w}:*" if len(w) >= 4 else w for w in words)


@dataclass
class Hit:
    chunk: DocumentChunk
    document: Document
    score: float = 0.0
    keyword_rank: int | None = None
    semantic_rank: int | None = None
    similarity: float | None = None
    sources: list[str] = field(default_factory=list)


@dataclass
class Retrieval:
    hits: list[Hit]
    semantic: str  # completed | not_configured | failed | no_vectors
    detail: str | None = None


def retrieve(db: Session, tenant_id: uuid.UUID, query: str, *, limit: int = 8, scope: dict[str, Any] | None = None,
             user_id: uuid.UUID | None = None, key: str, candidates: int = 40) -> Retrieval:
    visible = visible_documents(tenant_id, scope)
    ranked: dict[uuid.UUID, Hit] = {}

    tsq = keyword_query(query)
    if tsq:
        q = func.to_tsquery("simple", tsq)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, q)
        rows = db.execute(
            select(DocumentChunk, Document, rank.label("rank")).join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.version_number == Document.current_version,
                   DocumentChunk.search_vector.op("@@")(q), visible)
            .order_by(literal_column("rank").desc(), DocumentChunk.chunk_index).limit(candidates)).all()
        for i, (chunk, doc, _r) in enumerate(rows, start=1):
            hit = ranked.setdefault(chunk.id, Hit(chunk=chunk, document=doc))
            hit.keyword_rank = i
            hit.score += 1 / (RRF_K + i)
            hit.sources.append("keyword")

    semantic, detail = "not_configured", None
    provider = embedding_provider(db, tenant_id)
    if provider is not None:
        has_vectors = db.scalar(select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.tenant_id == tenant_id, DocumentChunk.embedding_model == provider.embedding_model))
        if not has_vectors:
            semantic = "no_vectors"
        else:
            try:
                qv = _embed(db, tenant_id, provider, [query[:4000]], user_id=user_id, key=f"{key}:query")[0]
                distance = DocumentChunk.embedding.cosine_distance(qv)
                rows = db.execute(
                    select(DocumentChunk, Document, distance.label("distance"))
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.embedding_model == provider.embedding_model,
                           DocumentChunk.version_number == Document.current_version,
                           func.vector_dims(DocumentChunk.embedding) == len(qv), visible)
                    .order_by(literal_column("distance")).limit(candidates)).all()
                from app.services.ai_service import get_setting

                floor = float(get_setting(db, tenant_id, "search.min_similarity", 0.25))
                rows = [r for r in rows if 1 - float(r[2]) >= floor]  # unrelated neighbours are not evidence
                for i, (chunk, doc, dist) in enumerate(rows, start=1):
                    hit = ranked.setdefault(chunk.id, Hit(chunk=chunk, document=doc))
                    hit.semantic_rank = i
                    hit.similarity = round(1 - float(dist), 4)
                    hit.score += 1 / (RRF_K + i)
                    hit.sources.append("semantic")
                semantic = "completed"
            except (AIProviderError, QuotaExceeded) as exc:
                semantic, detail = "failed", getattr(exc, "message", None) or str(exc)
    hits = sorted(ranked.values(), key=lambda h: h.score, reverse=True)[:limit]
    return Retrieval(hits=hits, semantic=semantic, detail=detail)


def search_documents(db: Session, tenant_id: uuid.UUID, query: str, *, limit: int = 20,
                     user_id: uuid.UUID | None = None, key: str) -> tuple[list[dict[str, Any]], Retrieval]:
    """Hybrid document search: chunks fused by RRF, grouped by document (best passage kept)."""
    retrieval = retrieve(db, tenant_id, query, limit=limit * 4, user_id=user_id, key=key, candidates=80)
    # title / file-name matches that have no text chunk still count (keyword side)
    tsq = keyword_query(query)
    title_rows: list[Document] = []
    if tsq:
        q = func.to_tsquery("simple", tsq)
        title_rows = list(db.scalars(select(Document).where(
            visible_documents(tenant_id), Document.search_vector.op("@@")(q))
            .order_by(func.ts_rank_cd(Document.search_vector, q).desc()).limit(limit)))
    best: dict[uuid.UUID, dict[str, Any]] = {}
    for hit in retrieval.hits:
        d = best.get(hit.document.id)
        if d is None:
            best[hit.document.id] = d = {"document": hit.document, "score": 0.0, "passage": hit.chunk.text,
                                         "page_from": hit.chunk.page_from, "page_to": hit.chunk.page_to,
                                         "match": set(), "similarity": hit.similarity}
        d["score"] += hit.score
        d["match"].update(hit.sources)
    for i, doc in enumerate(title_rows, start=1):
        d = best.setdefault(doc.id, {"document": doc, "score": 0.0, "passage": None, "page_from": None,
                                     "page_to": None, "match": set(), "similarity": None})
        d["score"] += 1 / (RRF_K + i)
        d["match"].add("keyword")
    results = sorted(best.values(), key=lambda d: d["score"], reverse=True)[:limit]
    for r in results:
        r["match"] = "both" if len(r["match"]) > 1 else (next(iter(r["match"])) if r["match"] else "keyword")
        r["score"] = round(r["score"], 5)
    return results, retrieval


def stats(db: Session, tenant_id: uuid.UUID) -> dict[str, Any]:
    provider = embedding_provider(db, tenant_id)
    total = db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id)) or 0
    cond = [DocumentChunk.tenant_id == tenant_id, DocumentChunk.embedding.is_not(None)]
    if provider is not None:
        cond.append(DocumentChunk.embedding_model == provider.embedding_model)
    embedded = db.scalar(select(func.count()).select_from(DocumentChunk).where(*cond)) or 0
    docs = db.scalar(select(func.count(func.distinct(DocumentChunk.document_id))).where(
        DocumentChunk.tenant_id == tenant_id)) or 0
    return {"chunks": total, "embedded_chunks": embedded, "indexed_documents": docs,
            "embedding_provider": provider.name if provider else None,
            "embedding_model": provider.embedding_model if provider else None}
