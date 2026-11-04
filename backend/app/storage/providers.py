"""Storage providers: local filesystem (dev only), S3 / S3-compatible, Azure Blob."""

from __future__ import annotations

import io
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.storage.base import StorageBackend, StorageError


class LocalStorage(StorageBackend):
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("Invalid storage key")  # path traversal guard
        return path

    def put(self, key: str, data: BinaryIO, *, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        with open(tmp, "wb") as fh:
            shutil.copyfileobj(data, fh, length=1024 * 1024)
        os.replace(tmp, path)

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        if not path.exists():
            raise StorageError(f"Object not found: {key}")
        return open(path, "rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3Storage(StorageBackend):
    name = "s3"

    def __init__(self, bucket: str, endpoint_url: str | None, region: str | None) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise StorageError("boto3 is required for the S3 storage provider") from exc
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def put(self, key: str, data: BinaryIO, *, content_type: str) -> None:
        self.client.upload_fileobj(data, self.bucket, key, ExtraArgs={
            "ContentType": content_type, "ServerSideEncryption": "AES256"})

    def open(self, key: str) -> BinaryIO:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"]  # type: ignore[no-any-return]

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False


class AzureBlobStorage(StorageBackend):
    name = "azure_blob"

    def __init__(self, connection_string: str, container: str) -> None:
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:  # pragma: no cover
            raise StorageError("azure-storage-blob is required for the Azure Blob provider") from exc
        self.container = BlobServiceClient.from_connection_string(connection_string).get_container_client(container)

    def put(self, key: str, data: BinaryIO, *, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self.container.upload_blob(key, data, overwrite=True,
                                   content_settings=ContentSettings(content_type=content_type))

    def open(self, key: str) -> BinaryIO:
        return io.BytesIO(self.container.download_blob(key).readall())

    def delete(self, key: str) -> None:
        self.container.delete_blob(key)

    def exists(self, key: str) -> bool:
        return bool(self.container.get_blob_client(key).exists())


@lru_cache
def get_storage(provider: str | None = None) -> StorageBackend:
    settings = get_settings()
    provider = provider or settings.storage_provider
    if provider == "local":
        if settings.environment == "prod":
            raise StorageError("Local storage is not allowed in production")
        return LocalStorage(settings.storage_local_root)
    if provider == "s3":
        if not settings.s3_bucket:
            raise StorageError("S3 storage selected but DOCUMIND_S3_BUCKET is not configured")
        return S3Storage(settings.s3_bucket, settings.s3_endpoint_url, settings.s3_region)
    if provider == "azure_blob":
        if not (settings.azure_blob_connection_string and settings.azure_blob_container):
            raise StorageError("Azure Blob storage selected but not configured")
        return AzureBlobStorage(settings.azure_blob_connection_string, settings.azure_blob_container)
    raise StorageError(f"Unknown storage provider '{provider}'")
