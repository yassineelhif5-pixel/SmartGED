from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models import DocumentStatus, MetadataDataType, StepStatus
from app.schemas.common import ORM


# ----------------------------------------------------------------- folders
class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=1000)


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    move_to_root: bool = False
    description: str | None = Field(default=None, max_length=1000)


class FolderOut(ORM):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    description: str | None
    created_at: datetime
    document_count: int = 0


# ------------------------------------------------------- document types
class MetadataDefinitionIn(BaseModel):
    id: uuid.UUID | None = None
    technical_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    display_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    data_type: MetadataDataType
    required: bool = False
    default_value: Any = None
    validation_rules: dict[str, Any] = Field(default_factory=dict)
    allowed_values: list[str] | None = None
    searchable: bool = True
    visible: bool = True
    ai_extraction_enabled: bool = True
    extraction_prompt: str | None = Field(default=None, max_length=4000)
    sensitive: bool = False
    requires_human_validation: bool = False


class MetadataDefinitionOut(ORM, MetadataDefinitionIn):
    id: uuid.UUID
    position: int


class DocumentTypeIn(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,59}$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    icon: str | None = Field(default=None, max_length=40)
    requires_validation: bool = False
    classification_hints: str | None = Field(default=None, max_length=4000)
    is_active: bool = True
    fields: list[MetadataDefinitionIn] = Field(default_factory=list)


class DocumentTypeOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    color: str | None
    icon: str | None
    schema_version: int
    requires_validation: bool
    classification_hints: str | None
    is_active: bool
    fields: list[MetadataDefinitionOut]
    document_count: int = 0


class DocumentTypeBrief(ORM):
    id: uuid.UUID
    code: str
    name: str
    color: str | None
    icon: str | None


# ------------------------------------------------------------- documents
class DocumentOut(ORM):
    id: uuid.UUID
    title: str
    file_name: str
    original_file_name: str
    mime_type: str
    extension: str
    file_size: int
    sha256: str
    page_count: int | None
    folder_id: uuid.UUID | None
    parent_document_id: uuid.UUID | None
    document_type: DocumentTypeBrief | None
    current_version: int
    owner_id: uuid.UUID | None
    status: DocumentStatus
    language: str | None
    scan_status: StepStatus
    ocr_status: StepStatus
    ai_status: StepStatus
    classification_status: StepStatus
    validation_status: StepStatus
    classification_confidence: float | None
    duplicate_of_id: uuid.UUID | None
    checked_out_by: uuid.UUID | None
    checked_out_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, v: Any) -> list[str]:
        return sorted(t.tag if hasattr(t, "tag") else str(t) for t in (v or []))


class MetadataValueOut(BaseModel):
    definition_id: uuid.UUID
    technical_name: str
    display_name: str
    data_type: MetadataDataType
    value: Any
    source: str
    confidence: float | None
    source_page: int | None
    source_text: str | None
    validation_status: StepStatus
    validated_at: datetime | None
    sensitive: bool
    required: bool
    display_value: str | None = None
    reference_type: str | None = None


class DocumentDetail(DocumentOut):
    metadata: list[MetadataValueOut]
    owner_name: str | None
    checked_out_by_name: str | None


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    folder_id: uuid.UUID | None = None
    move_to_root: bool = False
    document_type_id: uuid.UUID | None = None
    clear_document_type: bool = False
    tags: list[str] | None = Field(default=None, max_length=50)


class MetadataPatch(BaseModel):
    values: dict[str, Any]  # technical_name -> raw value
    validate_fields: list[str] = Field(default_factory=list)


class VersionOut(ORM):
    id: uuid.UUID
    version_number: int
    author_id: uuid.UUID | None
    comment: str | None
    change_reason: str | None
    file_name: str
    mime_type: str
    file_size: int
    sha256: str
    created_at: datetime


class OcrPageOut(ORM):
    page_number: int
    text: str
    method: str
    confidence: float | None


class JobOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    step: str
    status: StepStatus
    attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None
    result: dict | None


class RelationIn(BaseModel):
    target_document_id: uuid.UUID
    relation_type: str = Field(pattern=r"^[a-z_]{3,40}$")


class RelationOut(BaseModel):
    id: uuid.UUID
    relation_type: str
    direction: str
    document: DocumentOut


class CopyRequest(BaseModel):
    folder_id: uuid.UUID | None = None
