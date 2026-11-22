"""Encryption of tenant secrets (AI keys, connector credentials) at rest with Fernet (AES-128-CBC + HMAC)."""

from __future__ import annotations

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.encryption_key:
        return Fernet(settings.encryption_key.encode())
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"documind-secrets-v1",
                   info=b"tenant-secrets").derive(settings.secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Secret cannot be decrypted (encryption key changed?)") from exc


def hint(value: str) -> str:
    return f"…{value[-4:]}" if len(value) > 8 else "…"
