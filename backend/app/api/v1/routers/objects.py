"""Business objects (non-document elements) and their type designer.

Objects are reference data — suppliers, customers, projects, assets… — that can
be linked to documents, referenced by ``reference`` metadata fields and used to
fill a document's metadata automatically.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.database.session import get_db
from app.models import BusinessObject, MetadataDefinition, ObjectStatus, ObjectType
from app.repositories.base import get_owned
from app.schemas.common import Message, Page
from app.schemas.objects import (
    ApplyObjectIn,
    ApplyObjectOut,
    BusinessObjectIn,
    BusinessObjectOut,
    ObjectLinkIn,
    ObjectLinkOut,
    ObjectTypeIn,
    ObjectTypeOut,
)
from app.security.context import Principal, require
from app.services import object_service, schema_designer

router = APIRouter(tags=["Business objects"])


# ------------------------------------------------------------ object types
def _type_out(db: Session, t: ObjectType) -> ObjectTypeOut:
    count = db.scalar(select(func.count()).select_from(BusinessObject).where(BusinessObject.object_type_id == t.id)) or 0
    return ObjectTypeOut.model_validate(t).model_copy(update={"object_count": int(count)})


@router.get("/object-types", response_model=list[ObjectTypeOut])
def list_types(p: Principal = Depends(require("object_type:read")), db: Session = Depends(get_db)) -> list:
    return [_type_out(db, t) for t in db.scalars(select(ObjectType).where(ObjectType.tenant_id == p.tenant_id)
                                                 .order_by(ObjectType.name))]


@router.post("/object-types", response_model=ObjectTypeOut, status_code=201)
def create_type(body: ObjectTypeIn, p: Principal = Depends(require("object_type:create")),
                db: Session = Depends(get_db)) -> ObjectTypeOut:
    schema_designer.validate_fields(db, p.tenant_id, body.fields)
    if object_service.object_type_by_code(db, p.tenant_id, body.code):
        raise Conflict("An object type with this code already exists")
    t = ObjectType(tenant_id=p.tenant_id, **body.model_dump(exclude={"fields"}))
    db.add(t)
    db.flush()
    for pos, f in enumerate(body.fields):
        t.fields.append(MetadataDefinition(tenant_id=p.tenant_id, object_type_id=t.id, position=pos,
                                           **f.model_dump(exclude={"id"})))
    db.flush()
    p.audit(db, "object_type.created", resource_type="object_type", resource_id=t.id, details={"code": t.code})
    return _type_out(db, t)


@router.put("/object-types/{type_id}", response_model=ObjectTypeOut)
def update_type(type_id: uuid.UUID, body: ObjectTypeIn, p: Principal = Depends(require("object_type:update")),
                db: Session = Depends(get_db)) -> ObjectTypeOut:
    schema_designer.validate_fields(db, p.tenant_id, body.fields)
    t = get_owned(db, ObjectType, p.tenant_id, type_id, label="Object type")
    other = object_service.object_type_by_code(db, p.tenant_id, body.code)
    if other is not None and other.id != t.id:
        raise Conflict("An object type with this code already exists")
    for key, value in body.model_dump(exclude={"fields"}).items():
        setattr(t, key, value)
    kept, structural = schema_designer.sync_fields(t.fields, body.fields, tenant_id=p.tenant_id,
                                                   owner={"object_type_id": t.id})
    t.fields[:] = kept
    if structural:
        t.schema_version += 1
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise Conflict("Field definitions conflict (duplicate technical name?)") from exc
    p.audit(db, "object_type.updated", resource_type="object_type", resource_id=t.id,
            details={"schema_version": t.schema_version})
    return _type_out(db, t)


@router.delete("/object-types/{type_id}", response_model=Message)
def delete_type(type_id: uuid.UUID, p: Principal = Depends(require("object_type:delete")),
                db: Session = Depends(get_db)) -> Message:
    t = get_owned(db, ObjectType, p.tenant_id, type_id, label="Object type")
    count = db.scalar(select(func.count()).select_from(BusinessObject).where(BusinessObject.object_type_id == t.id)) or 0
    if count:
        t.is_active = False
        p.audit(db, "object_type.deactivated", resource_type="object_type", resource_id=t.id)
        return Message(message=f"{count} object(s) use this type: it has been deactivated instead of deleted")
    db.delete(t)
    p.audit(db, "object_type.deleted", resource_type="object_type", resource_id=type_id)
    return Message(message="Object type deleted")


# ----------------------------------------------------------------- objects
def _obj_out(obj: BusinessObject, count: int = 0) -> BusinessObjectOut:
    return BusinessObjectOut.model_validate(obj).model_copy(update={"document_count": count})


@router.get("/objects", response_model=Page[BusinessObjectOut])
def list_objects(p: Principal = Depends(require("business_object:read")), db: Session = Depends(get_db),
                 object_type_id: uuid.UUID | None = None, type_code: str | None = None,
                 q: str | None = Query(default=None, max_length=200), status: ObjectStatus | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)) -> Page[BusinessObjectOut]:
    if type_code and not object_type_id:
        t = object_service.object_type_by_code(db, p.tenant_id, type_code)
        if t is None:
            return Page(items=[], total=0, page=page, page_size=page_size)
        object_type_id = t.id
    items, total = object_service.search_objects(db, p.tenant_id, object_type_id=object_type_id, q=q,
                                                 status=status, page=page, page_size=page_size)
    counts = object_service.document_counts(db, [o.id for o in items])
    return Page(items=[_obj_out(o, counts.get(o.id, 0)) for o in items], total=total, page=page, page_size=page_size)


@router.get("/objects/{object_id}", response_model=BusinessObjectOut)
def get_object(object_id: uuid.UUID, p: Principal = Depends(require("business_object:read")),
               db: Session = Depends(get_db)) -> BusinessObjectOut:
    obj = get_owned(db, BusinessObject, p.tenant_id, object_id, label="Object")
    return _obj_out(obj, object_service.document_counts(db, [obj.id]).get(obj.id, 0))


@router.post("/objects", response_model=BusinessObjectOut, status_code=201)
def create_object(body: BusinessObjectIn, p: Principal = Depends(require("business_object:create")),
                  db: Session = Depends(get_db)) -> BusinessObjectOut:
    obj = object_service.save_object(db, p.tenant_id, p.user.id, object_id=None, **body.model_dump())
    p.audit(db, "object.created", resource_type="business_object", resource_id=obj.id,
            details={"type": obj.object_type.code, "code": obj.code})
    return _obj_out(obj)


@router.put("/objects/{object_id}", response_model=BusinessObjectOut)
def update_object(object_id: uuid.UUID, body: BusinessObjectIn,
                  p: Principal = Depends(require("business_object:update")),
                  db: Session = Depends(get_db)) -> BusinessObjectOut:
    obj = object_service.save_object(db, p.tenant_id, p.user.id, object_id=object_id, **body.model_dump())
    p.audit(db, "object.updated", resource_type="business_object", resource_id=obj.id)
    return _obj_out(obj, object_service.document_counts(db, [obj.id]).get(obj.id, 0))


@router.delete("/objects/{object_id}", response_model=Message)
def delete_object(object_id: uuid.UUID, p: Principal = Depends(require("business_object:delete")),
                  db: Session = Depends(get_db)) -> Message:
    linked = object_service.delete_object(db, p.tenant_id, object_id)
    p.audit(db, "object.archived" if linked else "object.deleted", resource_type="business_object",
            resource_id=object_id)
    if linked:
        return Message(message=f"Linked to {linked} document(s): the object has been archived instead of deleted")
    return Message(message="Object deleted")


# ------------------------------------------------- document ↔ object links
@router.get("/documents/{document_id}/objects", response_model=list[ObjectLinkOut])
def document_objects(document_id: uuid.UUID, p: Principal = Depends(require("document:read", "business_object:read")),
                     db: Session = Depends(get_db)) -> list[ObjectLinkOut]:
    links = object_service.links_of_document(db, p.tenant_id, document_id)
    counts = object_service.document_counts(db, [lk.object_id for lk in links])
    return [ObjectLinkOut(id=lk.id, role=lk.role, object=_obj_out(lk.object, counts.get(lk.object_id, 0)))
            for lk in links]


@router.post("/documents/{document_id}/objects", response_model=Message, status_code=201)
def link_object(document_id: uuid.UUID, body: ObjectLinkIn,
                p: Principal = Depends(require("document:update", "business_object:read")),
                db: Session = Depends(get_db)) -> Message:
    lk = object_service.link(db, p.tenant_id, document_id, body.object_id, body.role, p.user.id)
    p.audit(db, "document.object_linked", resource_type="document", resource_id=document_id,
            details={"object_id": str(body.object_id), "role": body.role, "link_id": str(lk.id)})
    return Message(message="Object linked")


@router.delete("/documents/{document_id}/objects/{link_id}", response_model=Message)
def unlink_object(document_id: uuid.UUID, link_id: uuid.UUID, p: Principal = Depends(require("document:update")),
                  db: Session = Depends(get_db)) -> Message:
    object_service.unlink(db, p.tenant_id, document_id, link_id)
    p.audit(db, "document.object_unlinked", resource_type="document", resource_id=document_id,
            details={"link_id": str(link_id)})
    return Message(message="Link removed")


@router.post("/documents/{document_id}/apply-object", response_model=ApplyObjectOut)
def apply_object(document_id: uuid.UUID, body: ApplyObjectIn,
                 p: Principal = Depends(require("metadata:update", "business_object:read")),
                 db: Session = Depends(get_db)) -> ApplyObjectOut:
    filled, skipped = object_service.apply_to_document(db, p.tenant_id, document_id, body.object_id, p.user.id,
                                                       overwrite=body.overwrite, mapping=body.mapping)
    p.audit(db, "document.metadata_filled_from_object", resource_type="document", resource_id=document_id,
            details={"object_id": str(body.object_id), "filled": filled})
    return ApplyObjectOut(filled=filled, skipped=skipped)
