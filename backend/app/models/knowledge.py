"""Knowledge layer (phase 4): document chunks with full-text + vector search, and Lina conversations.

Chunks are always created from the OCR text (keyword retrieval works without AI). Embeddings are
added only when the organisation configured an embeddings-capable provider; the vector column is
dimension-free so the organisation can pick its model (exact cosine search, filtered by tenant).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TenantScoped, Timestamps, UUIDPk


class DocumentChunk(UUIDPk, TenantScoped, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document", "document_id", "version_number", "chunk_index"),
        Index("ix_document_chunks_search", "search_vector", postgresql_using="gin"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True))


class LinaConversation(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "lina_conversations"
    __table_args__ = (Index("ix_lina_conversations_user", "tenant_id", "user_id"),
                      Index("ix_lina_conversations_user_id_fk", "user_id"))

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {document_ids, folder_id}

    messages: Mapped[list[LinaMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="LinaMessage.created_at")


class LinaMessage(UUIDPk, TenantScoped, Base):
    __tablename__ = "lina_messages"
    __table_args__ = (Index("ix_lina_messages_conversation", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lina_conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped[LinaConversation] = relationship(back_populates="messages")
