"""Document views: shared filters configured by tenant admins + personal filters per user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import DocumentView, ViewScope
from app.schemas.common import Message
from app.schemas.views import DefaultViewIn, DocumentFilters, DocumentViewIn, DocumentViewOut, ViewsResponse
from app.security.context import Principal, require
from app.services import view_service

router = APIRouter(prefix="/document-views", tags=["Document views"])
ADMIN = "document_view:administer"


def _out(v: DocumentView, p: Principal) -> DocumentViewOut:
    mine = v.scope == ViewScope.personal and v.owner_id == p.user.id
    return DocumentViewOut(
        id=v.id, name=v.name, description=v.description, icon=v.icon, scope=v.scope,
        filters=DocumentFilters.model_validate(v.filters), is_default=v.is_default, position=v.position,
        is_mine=mine, can_edit=mine or (v.scope == ViewScope.tenant and p.can(ADMIN)),
    )


@router.get("", response_model=ViewsResponse)
def list_views(p: Principal = Depends(require("document:read")), db: Session = Depends(get_db)) -> ViewsResponse:
    views = view_service.visible_views(db, p.tenant_id, p.user.id)
    default_id, source = view_service.resolve_default(db, p.tenant_id, p.user.id, views)
    return ViewsResponse(views=[_out(v, p) for v in views], default_view_id=default_id, default_source=source)


@router.post("", response_model=DocumentViewOut, status_code=201)
def create_view(body: DocumentViewIn, p: Principal = Depends(require("document:read")),
                db: Session = Depends(get_db)) -> DocumentViewOut:
    view = view_service.create_view(db, p.tenant_id, p.user.id, p.can(ADMIN), **body.model_dump(exclude={"filters"}),
                                    filters=body.filters)
    p.audit(db, "document_view.created", resource_type="document_view", resource_id=view.id,
            details={"scope": view.scope.value, "name": view.name, "default": view.is_default})
    return _out(view, p)


@router.put("/{view_id}", response_model=DocumentViewOut)
def update_view(view_id: uuid.UUID, body: DocumentViewIn, p: Principal = Depends(require("document:read")),
                db: Session = Depends(get_db)) -> DocumentViewOut:
    view = view_service.update_view(db, p.tenant_id, p.user.id, p.can(ADMIN), view_id,
                                    **body.model_dump(exclude={"filters"}), filters=body.filters)
    p.audit(db, "document_view.updated", resource_type="document_view", resource_id=view.id,
            details={"scope": view.scope.value, "default": view.is_default})
    return _out(view, p)


@router.delete("/{view_id}", response_model=Message)
def delete_view(view_id: uuid.UUID, p: Principal = Depends(require("document:read")),
                db: Session = Depends(get_db)) -> Message:
    view_service.delete_view(db, p.tenant_id, p.user.id, p.can(ADMIN), view_id)
    p.audit(db, "document_view.deleted", resource_type="document_view", resource_id=view_id)
    return Message(message="View deleted")


@router.put("/me/default", response_model=Message)
def set_my_default(body: DefaultViewIn, p: Principal = Depends(require("document:read")),
                   db: Session = Depends(get_db)) -> Message:
    view_service.set_user_default(db, p.tenant_id, p.user.id, body.view_id)
    return Message(message="Default view saved")


@router.delete("/me/default", response_model=Message)
def reset_my_default(p: Principal = Depends(require("document:read")), db: Session = Depends(get_db)) -> Message:
    view_service.set_user_default(db, p.tenant_id, p.user.id, None, reset=True)
    return Message(message="Back to the organisation default")
