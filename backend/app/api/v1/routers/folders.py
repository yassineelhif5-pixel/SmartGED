from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import Message
from app.schemas.ged import FolderCreate, FolderOut, FolderUpdate
from app.security.context import Principal, require
from app.services import folder_service

router = APIRouter(prefix="/folders", tags=["Folders"])


def _out(folder, count: int = 0) -> FolderOut:  # type: ignore[no-untyped-def]
    return FolderOut.model_validate(folder).model_copy(update={"document_count": count})


@router.get("", response_model=list[FolderOut])
def list_folders(p: Principal = Depends(require("folder:read")), db: Session = Depends(get_db)) -> list[FolderOut]:
    return [_out(f, c) for f, c in folder_service.list_folders(db, p.tenant_id)]


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(body: FolderCreate, p: Principal = Depends(require("folder:create")),
                  db: Session = Depends(get_db)) -> FolderOut:
    folder = folder_service.create_folder(db, p.tenant_id, p.user.id, body.name, body.parent_id, body.description)
    p.audit(db, "folder.created", resource_type="folder", resource_id=folder.id, details={"name": folder.name})
    return _out(folder)


@router.patch("/{folder_id}", response_model=FolderOut)
def update_folder(folder_id: uuid.UUID, body: FolderUpdate, p: Principal = Depends(require("folder:update")),
                  db: Session = Depends(get_db)) -> FolderOut:
    folder = folder_service.update_folder(db, p.tenant_id, folder_id, name=body.name, parent_id=body.parent_id,
                                          move_to_root=body.move_to_root, description=body.description)
    p.audit(db, "folder.updated", resource_type="folder", resource_id=folder.id,
            details=body.model_dump(exclude_none=True, mode="json"))
    return _out(folder)


@router.delete("/{folder_id}", response_model=Message)
def delete_folder(folder_id: uuid.UUID, p: Principal = Depends(require("folder:delete", "document:delete")),
                  db: Session = Depends(get_db)) -> Message:
    trashed = folder_service.delete_folder(db, p.tenant_id, folder_id)
    p.audit(db, "folder.deleted", resource_type="folder", resource_id=folder_id, details={"documents_trashed": trashed})
    return Message(message=f"Folder deleted, {trashed} document(s) moved to the trash")
