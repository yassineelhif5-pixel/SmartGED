"""Shared field-designer logic for document types and business-object types."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.models import MetadataDataType, MetadataDefinition, ObjectType

STRUCTURAL = ("technical_name", "data_type", "required", "allowed_values", "validation_rules")


def validate_fields(db: Session, tenant_id: uuid.UUID, fields: Sequence) -> None:  # type: ignore[type-arg]
    names = [f.technical_name for f in fields]
    if len(names) != len(set(names)):
        raise ValidationFailed("Field technical names must be unique within a type")
    for f in fields:
        if f.data_type in (MetadataDataType.dropdown, MetadataDataType.multi_select) and not f.allowed_values:
            raise ValidationFailed(f"{f.display_name}: a list field needs allowed values")
        if f.data_type == MetadataDataType.reference:
            code = (f.validation_rules or {}).get("object_type_code")
            if code:
                from sqlalchemy import select

                if db.scalar(select(ObjectType.id).where(ObjectType.tenant_id == tenant_id,
                                                         ObjectType.code == code)) is None:
                    raise ValidationFailed(f"{f.display_name}: unknown object type '{code}'")


def sync_fields(current: list[MetadataDefinition], incoming: Sequence, *, tenant_id: uuid.UUID,  # type: ignore[type-arg]
                owner: dict[str, uuid.UUID]) -> tuple[list[MetadataDefinition], bool]:
    """Return the new ordered field list and whether the change is structural (→ schema version bump)."""
    existing = {f.id: f for f in current}
    structural = False
    kept: list[MetadataDefinition] = []
    for pos, f in enumerate(incoming):
        data = f.model_dump(exclude={"id"})
        if f.id and f.id in existing:
            row = existing[f.id]
            if any(getattr(row, k) != data[k] for k in STRUCTURAL):
                structural = True
            for k, v in data.items():
                setattr(row, k, v)
            row.position = pos
        else:
            row = MetadataDefinition(tenant_id=tenant_id, position=pos, **owner, **data)
            structural = True
        kept.append(row)
    if len(kept) != len(existing) or any(k.id not in existing for k in kept if k.id):
        structural = True
    return kept, structural
