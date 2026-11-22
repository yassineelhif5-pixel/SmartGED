"""Application settings, loaded from environment variables (12-factor).

Secrets are never hard-coded: every sensitive value comes from the environment
or a secret manager mounted as env vars.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCUMIND_", extra="ignore")

    # --- General -----------------------------------------------------------
    app_name: str = "DocuMind AI"
    environment: Literal["dev", "test", "uat", "prod"] = "dev"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql+psycopg://documind:documind@localhost:5432/documind"
    # Optional dedicated PostgreSQL schema (e.g. "smartged" on a shared Supabase project).
    # Every table, enum and the alembic_version table live in it; search_path is set per connection.
    db_schema: str | None = Field(default=None, pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Redis / Celery ----------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_eager: bool = False  # run tasks inline (tests / single-process dev)

    # --- Security ----------------------------------------------------------
    secret_key: str = Field(default="change-me-in-env", min_length=16)
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    jwt_algorithm: str = "HS256"
    login_rate_limit_per_minute: int = 10
    password_min_length: int = 10
    secure_cookies: bool = True

    # --- Storage -----------------------------------------------------------
    storage_provider: Literal["local", "s3", "azure_blob"] = "local"
    storage_local_root: str = "./data/storage"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    azure_blob_connection_string: str | None = None
    azure_blob_container: str | None = None

    # --- Uploads -----------------------------------------------------------
    max_upload_mb: int = 100
    allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "pdf", "png", "jpg", "jpeg", "tif", "tiff", "txt", "csv", "md",
            "docx", "xlsx", "pptx", "eml",
        ]
    )

    # --- OCR / antivirus ---------------------------------------------------
    ocr_provider: Literal["tesseract", "azure_di", "none"] = "tesseract"
    ocr_languages: str = "fra+eng"
    ocr_min_text_chars_per_page: int = 40  # below → page is considered scanned
    clamav_host: str | None = None
    clamav_port: int = 3310

    # --- AI ---------------------------------------------------------------
    # Key encrypting tenant AI provider secrets (Fernet, urlsafe base64 32 bytes).
    # If unset, a key is derived from DOCUMIND_SECRET_KEY (rotate both together).
    encryption_key: str | None = None
    ai_max_retries: int = 3
    ai_retry_base_seconds: float = 1.0
    ai_max_document_chars: int = 60_000

    # --- Bootstrap ---------------------------------------------------------
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    @field_validator("cors_origins", "allowed_extensions", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            if v.strip().startswith("["):
                import json

                return json.loads(v)
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def db_connect_args(self) -> dict[str, str]:
        return {"options": f"-csearch_path={self.db_schema},public"} if self.db_schema else {}

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment in ("uat", "prod") and settings.secret_key == "change-me-in-env":
        raise RuntimeError("DOCUMIND_SECRET_KEY must be set in UAT/PROD environments")
    return settings
