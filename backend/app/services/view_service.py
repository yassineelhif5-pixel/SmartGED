"""Saved document views: shared (tenant) views administered by admins, personal views per user."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.models import BusinessObject, DocumentType, DocumentView, Folder, UserPreference, ViewScope
from app.repositories.base import get_owned
from app.schemas.views import DocumentFilters

DEFAULT_VIEW_KEY = "documents.default_view"
MAX_PERSONAL_VIEWS = 50


def visible_views(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[DocumentView]:
    return list(db.scalars(
        select(DocumentView)
        .where(DocumentView.tenant_id == tenant_id,
               or_(DocumentView.scope == ViewScope.tenant, DocumentView.owner_id == user_id))
        .order_by(DocumentView.scope, DocumentView.position, DocumentView.name)
    ))


def get_visible(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, view_id: uuid.UUID) -> DocumentView:
    view = db.scalar(select(DocumentView).where(DocumentView.id == view_id, DocumentView.tenant_id == tenant_id))
    if view is None or (view.scope == ViewScope.personal and view.owner_id != user_id):
        raise NotFound("View not found")  # someone else's personal view is indistinguishable from a missing one
    return view


def _check_editable(view: DocumentView, user_id: uuid.UUID, can_admin: bool) -> None:
    if view.scope == ViewScope.tenant and not can_admin:
        raise Forbidden("Only administrators can change shared views", code="permission_denied")


def _validate_filters(db: Session, tenant_id: uuid.UUID, filters: DocumentFilters) -> dict:
    """References inside a view must belong to the tenant (no cross-tenant ids stored)."""
    if filters.folder_id:
        get_owned(db, Folder, tenant_id, filters.folder_id, label="Folder")
    if filters.document_type_id:
        get_owned(db, DocumentType, tenant_id, filters.document_type_id, label="Document type")
    if filters.object_id:
        get_owned(db, BusinessObject, tenant_id, filters.object_id, label="Business object")
    return filters.model_dump(mode="json", exclude_defaults=False)


def _clear_tenant_default(db: Session, tenant_id: uuid.UUID, keep: uuid.UUID | None) -> None:
    for v in db.scalars(select(DocumentView).where(DocumentView.tenant_id == tenant_id,
                                                   DocumentView.scope == ViewScope.tenant,
                                                   DocumentView.is_default.is_(True))):
        if v.id != keep:
            v.is_default = False
    db.flush()


def create_view(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, can_admin: bool, *, name: str,
                description: str | None, icon: str | None, scope: ViewScope, filters: DocumentFilters,
                is_default: bool, position: int) -> DocumentView:
    if scope == ViewScope.tenant and not can_admin:
        raise Forbidden("Only administrators can create shared views", code="permission_denied")
    if scope == ViewScope.personal:
        count = len([v for v in visible_views(db, tenant_id, user_id) if v.owner_id == user_id])
        if count >= MAX_PERSONAL_VIEWS:
            raise ValidationFailed(f"At most {MAX_PERSONAL_VIEWS} personal views")
    view = DocumentView(
        tenant_id=tenant_id, scope=scope, owner_id=user_id if scope == ViewScope.personal else None,
        name=name.strip(), description=description, icon=icon, filters=_validate_filters(db, tenant_id, filters),
        is_default=is_default and scope == ViewScope.tenant, position=position, created_by=user_id,
    )
    if view.is_default:
        _clear_tenant_default(db, tenant_id, None)
    db.add(view)
    db.flush()
    return view


def update_view(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, can_admin: bool, view_id: uuid.UUID, *,
                name: str, description: str | None, icon: str | None, scope: ViewScope, filters: DocumentFilters,
                is_default: bool, position: int) -> DocumentView:
    view = get_visible(db, tenant_id, user_id, view_id)
    _check_editable(view, user_id, can_admin)
    if scope != view.scope:
        # Promoting a personal view to a shared one (or the reverse) is an admin action.
        if not can_admin:
            raise Forbidden("Only administrators can share a view", code="permission_denied")
        view.scope = scope
        view.owner_id = user_id if scope == ViewScope.personal else None
    view.name = name.strip()
    view.description = description
    view.icon = icon
    view.position = position
    view.filters = _validate_filters(db, tenant_id, filters)
    want_default = is_default and view.scope == ViewScope.tenant
    if want_default and not view.is_default:
        _clear_tenant_default(db, tenant_id, view.id)
    view.is_default = want_default
    db.flush()
    return view


def delete_view(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, can_admin: bool, view_id: uuid.UUID) -> None:
    view = get_visible(db, tenant_id, user_id, view_id)
    _check_editable(view, user_id, can_admin)
    # drop preferences pointing at it
    for pref in db.scalars(select(UserPreference).where(UserPreference.tenant_id == tenant_id,
                                                        UserPreference.key == DEFAULT_VIEW_KEY)):
        if pref.value == str(view_id):
            db.delete(pref)
    db.delete(view)
    db.flush()


def resolve_default(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID,
                    views: list[DocumentView]) -> tuple[uuid.UUID | None, str]:
    ids = {v.id for v in views}
    pref = db.scalar(select(UserPreference).where(UserPreference.tenant_id == tenant_id,
                                                  UserPreference.user_id == user_id,
                                                  UserPreference.key == DEFAULT_VIEW_KEY))
    if pref is not None:
        if pref.value is None:
            return None, "user"  # user explicitly chose "no default"
        try:
            vid = uuid.UUID(str(pref.value))
        except ValueError:
            vid = None
        if vid in ids:
            return vid, "user"
    tenant_default = next((v.id for v in views if v.scope == ViewScope.tenant and v.is_default), None)
    return (tenant_default, "tenant") if tenant_default else (None, "none")


def set_user_default(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, view_id: uuid.UUID | None,
                     reset: bool = False) -> None:
    pref = db.scalar(select(UserPreference).where(UserPreference.tenant_id == tenant_id,
                                                  UserPreference.user_id == user_id,
                                                  UserPreference.key == DEFAULT_VIEW_KEY))
    if reset:
        if pref is not None:
            db.delete(pref)
        db.flush()
        return
    if view_id is not None:
        get_visible(db, tenant_id, user_id, view_id)
    value = str(view_id) if view_id else None
    if pref is None:
        db.add(UserPreference(tenant_id=tenant_id, user_id=user_id, key=DEFAULT_VIEW_KEY, value=value))
    else:
        pref.value = value
    db.flush()
