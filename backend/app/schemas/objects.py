from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import ObjectStatus
from app.schemas.common import ORM
from app.schemas.ged import MetadataDefinitionIn, MetadataDefinitionOut


class ObjectTypeIn(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,59}$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    icon: str | None = Field(default=None, max_length=40)
    is_active: bool = True
    fields: list[MetadataDefinitionIn] = Field(default_factory=list)


class ObjectTypeOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    color: str | None
    icon: str | None
    schema_version: int
    is_active: bool
    fields: list[MetadataDefinitionOut]
    object_count: int = 0


class ObjectTypeBrief(ORM):
    id: uuid.UUID
    code: str
    name: str
    color: str | None
    icon: str | None


class BusinessObjectIn(BaseModel):
    object_type_id: uuid.UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    status: ObjectStatus = ObjectStatus.active
    attributes: dict[str, Any] = Field(default_factory=dict)


class BusinessObjectOut(ORM):
    id: uuid.UUID
    object_type: ObjectTypeBrief
    code: str
    name: str
    description: str | None
    status: ObjectStatus
    attributes: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    document_count: int = 0


class ObjectLinkIn(BaseModel):
    object_id: uuid.UUID
    role: str = Field(default="related", pattern=r"^[a-z][a-z0-9_]{1,79}$")


class ObjectLinkOut(BaseModel):
    id: uuid.UUID
    role: str
    object: BusinessObjectOut


class ApplyObjectIn(BaseModel):
    object_id: uuid.UUID
    overwrite: bool = False
    mapping: dict[str, str] = Field(default_factory=dict,
                                    description="document field -> object attribute (or 'name'/'code')")


class ApplyObjectOut(BaseModel):
    filled: list[str]
    skipped: list[str]
