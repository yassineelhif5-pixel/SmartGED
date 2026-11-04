"""Upload inspection: magic-byte sniffing, extension allow-list, safe file names, hashing."""

from __future__ import annotations

import hashlib
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.errors import ValidationFailed

_SIGNATURES: list[tuple[bytes, str, set[str]]] = [
    (b"%PDF-", "application/pdf", {"pdf"}),
    (b"\x89PNG\r\n\x1a\n", "image/png", {"png"}),
    (b"\xff\xd8\xff", "image/jpeg", {"jpg", "jpeg"}),
    (b"II*\x00", "image/tiff", {"tif", "tiff"}),
    (b"MM\x00*", "image/tiff", {"tif", "tiff"}),
]
_OOXML = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_TEXT = {"txt": "text/plain", "csv": "text/csv", "md": "text/markdown", "eml": "message/rfc822"}
_DANGEROUS_IN_TEXT = (b"<script", b"MZ\x90\x00")


@dataclass
class InspectedFile:
    path: Path
    size: int
    sha256: str
    mime_type: str
    extension: str
    safe_name: str


def safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFKC", Path(name or "document").name)
    name = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", "_", name).strip(" .") or "document"
    return name[:200]


def spool_and_hash(stream: BinaryIO, max_bytes: int) -> tuple[Path, int, str]:
    """Copy an upload to a temp file while hashing; abort as soon as it is too large."""
    digest = hashlib.sha256()
    size = 0
    tmp = tempfile.NamedTemporaryFile(prefix="documind-", delete=False)
    try:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ValidationFailed(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit", code="file_too_large")
            digest.update(chunk)
            tmp.write(chunk)
    except Exception:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        raise
    tmp.close()
    return Path(tmp.name), size, digest.hexdigest()


def detect_type(path: Path, extension: str) -> str:
    with open(path, "rb") as fh:
        head = fh.read(4096)
    for magic, mime, exts in _SIGNATURES:
        if head.startswith(magic):
            if extension not in exts:
                raise ValidationFailed("File content does not match its extension", code="mime_mismatch")
            return mime
    if extension in _OOXML:
        if not zipfile.is_zipfile(path):
            raise ValidationFailed("Invalid Office document", code="mime_mismatch")
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "[Content_Types].xml" not in names:
                raise ValidationFailed("Invalid Office document", code="mime_mismatch")
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise ValidationFailed("Macro-enabled documents are not accepted", code="macro_rejected")
        return _OOXML[extension]
    if extension in _TEXT:
        if b"\x00" in head or any(sig in head.lower() for sig in _DANGEROUS_IN_TEXT):
            raise ValidationFailed("Text file contains binary or active content", code="mime_mismatch")
        return _TEXT[extension]
    raise ValidationFailed("Unsupported or unrecognised file type", code="unsupported_type")


def inspect_upload(stream: BinaryIO, filename: str) -> InspectedFile:
    settings = get_settings()
    name = safe_filename(filename)
    extension = Path(name).suffix.lower().lstrip(".")
    if extension not in settings.allowed_extensions:
        raise ValidationFailed(f"Extension '.{extension}' is not allowed", code="extension_not_allowed")
    path, size, sha = spool_and_hash(stream, settings.max_upload_bytes)
    if size == 0:
        path.unlink(missing_ok=True)
        raise ValidationFailed("Empty file", code="empty_file")
    try:
        mime = detect_type(path, extension)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return InspectedFile(path=path, size=size, sha256=sha, mime_type=mime, extension=extension, safe_name=name)
