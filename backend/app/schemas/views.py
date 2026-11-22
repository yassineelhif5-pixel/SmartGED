from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import DocumentStatus, ViewScope


class DocumentFilters(BaseModel):
    """Every criterion the document explorer understands. Stored as JSON in a view."""

    q: str | None = Field(default=None, max_length=300)
    folder_id: uuid.UUID | None = None
    recursive: bool = True
    document_type_id: uuid.UUID | None = None
    status: DocumentStatus | None = None
    tag: str | None = Field(default=None, max_length=80)
    mine: bool = False
    object_id: uuid.UUID | None = None
    created_from: date | None = None
    created_to: date | None = None
    meta: dict[str, str] = Field(default_factory=dict, description="technical_name -> contains value")
    sort: Literal["created_at", "updated_at", "title", "file_size", "status", "relevance"] = "created_at"
    order: Literal["asc", "desc"] = "desc"

    @field_validator("meta")
    @classmethod
    def _meta(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 10:
            raise ValueError("at most 10 metadata filters")
        return {k[:80]: str(val)[:200] for k, val in v.items() if str(val).strip()}


class DocumentViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=40)
    scope: ViewScope = ViewScope.personal
    filters: DocumentFilters
    is_default: bool = Field(default=False, description="Tenant scope only: default view of the organisation")
    position: int = 0


class DocumentViewOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    icon: str | None
    scope: ViewScope
    filters: DocumentFilters
    is_default: bool
    position: int
    is_mine: bool
    can_edit: bool


class ViewsResponse(BaseModel):
    views: list[DocumentViewOut]
    default_view_id: uuid.UUID | None
    default_source: Literal["user", "tenant", "none"]


class DefaultViewIn(BaseModel):
    view_id: uuid.UUID | None
