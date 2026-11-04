"""Object storage abstraction. Binaries never go into PostgreSQL; only their keys do."""

from __future__ import annotations

import abc
from collections.abc import Iterator
from typing import BinaryIO


class StorageError(RuntimeError):
    pass


class StorageBackend(abc.ABC):
    name: str

    @abc.abstractmethod
    def put(self, key: str, data: BinaryIO, *, content_type: str) -> None: ...

    @abc.abstractmethod
    def open(self, key: str) -> BinaryIO: ...

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...

    @abc.abstractmethod
    def exists(self, key: str) -> bool: ...

    def iter_chunks(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        with self.open(key) as fh:
            while chunk := fh.read(chunk_size):
                yield chunk

    def health(self) -> dict[str, object]:
        return {"provider": self.name, "status": "ok"}


def object_key(tenant_id: object, document_id: object, version: int, sha256: str, extension: str) -> str:
    """Deterministic, tenant-partitioned key. Content-addressed per version for integrity checks."""
    ext = f".{extension}" if extension else ""
    return f"tenants/{tenant_id}/documents/{document_id}/v{version}/{sha256}{ext}"
