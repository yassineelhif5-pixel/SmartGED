"""Document Splitting Engine: proposals to cut a multi-document PDF (scan batch) into child documents.

A proposal is never applied silently: it is reviewed in the validation UI (or auto-applied only when
the organisation configured ``splitting.auto_apply_threshold`` and the detection is confident enough).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TenantScoped, Timestamps, UUIDPk


class SplitStatus(str, enum.Enum):
    proposed = "proposed"
    applied = "applied"
    dismissed = "dismissed"
    superseded = "superseded"


class DocumentSplitProposal(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "document_split_proposals"
    __table_args__ = (
        Index("ix_document_split_proposals_document", "document_id", "status"),
        Index("ix_document_split_proposals_decided_by_fk", "decided_by"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SplitStatus] = mapped_column(
        Enum(SplitStatus, name="split_status"), nullable=False, default=SplitStatus.proposed)
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # heuristic | ai | manual
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # [{start_page, end_page, title, document_type_code, document_type_id, confidence, reasons: [...]}]
    segments: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    separator_pages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    child_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
