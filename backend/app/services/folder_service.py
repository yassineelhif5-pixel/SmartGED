"""Folder hierarchy management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ValidationFailed
from app.models import Document, Folder
from app.repositories.base import get_owned


def list_folders(db: Session, tenant_id: uuid.UUID) -> list[tuple[Folder, int]]:
    counts = dict(
        db.execute(
            select(Document.folder_id, func.count())
            .where(Document.tenant_id == tenant_id, Document.deleted_at.is_(None))
            .group_by(Document.folder_id)
        ).all()
    )
    folders = db.scalars(
        select(Folder).where(Folder.tenant_id == tenant_id, Folder.deleted_at.is_(None)).order_by(func.lower(Folder.name))
    ).all()
    return [(f, int(counts.get(f.id, 0))) for f in folders]


def _descendant_ids(db: Session, tenant_id: uuid.UUID, root_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.execute(
        select(Folder.id, Folder.parent_id).where(Folder.tenant_id == tenant_id, Folder.deleted_at.is_(None))
    ).all()
    children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for fid, pid in rows:
        children.setdefault(pid, []).append(fid)
    out, stack = set(), [root_id]
    while stack:
        current = stack.pop()
        out.add(current)
        stack.extend(children.get(current, []))
    return out


def create_folder(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, name: str,
                  parent_id: uuid.UUID | None, description: str | None) -> Folder:
    if parent_id:
        get_owned(db, Folder, tenant_id, parent_id, label="Parent folder")
    folder = Folder(tenant_id=tenant_id, parent_id=parent_id, name=name.strip(), description=description,
                    created_by=user_id)
    db.add(folder)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise Conflict("A folder with this name already exists here", code="folder_exists") from exc
    return folder


def update_folder(db: Session, tenant_id: uuid.UUID, folder_id: uuid.UUID, *, name: str | None,
                  parent_id: uuid.UUID | None, move_to_root: bool, description: str | None) -> Folder:
    folder = get_owned(db, Folder, tenant_id, folder_id, label="Folder")
    if name is not None:
        folder.name = name.strip()
    if description is not None:
        folder.description = description
    if move_to_root:
        folder.parent_id = None
    elif parent_id is not None and parent_id != folder.parent_id:
        get_owned(db, Folder, tenant_id, parent_id, label="Target folder")
        if parent_id in _descendant_ids(db, tenant_id, folder.id):
            raise ValidationFailed("A folder cannot be moved into itself or one of its sub-folders")
        folder.parent_id = parent_id
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise Conflict("A folder with this name already exists here", code="folder_exists") from exc
    return folder


def delete_folder(db: Session, tenant_id: uuid.UUID, folder_id: uuid.UUID) -> int:
    """Soft-delete a folder subtree; its documents go to the trash. Returns trashed document count."""
    get_owned(db, Folder, tenant_id, folder_id, label="Folder")
    ids = _descendant_ids(db, tenant_id, folder_id)
    now = datetime.now(UTC)
    docs = db.scalars(select(Document).where(Document.tenant_id == tenant_id, Document.folder_id.in_(ids),
                                             Document.deleted_at.is_(None))).all()
    for doc in docs:
        doc.deleted_at = now
    for folder in db.scalars(select(Folder).where(Folder.id.in_(ids), Folder.tenant_id == tenant_id)).all():
        folder.deleted_at = now
    db.flush()
    return len(docs)
