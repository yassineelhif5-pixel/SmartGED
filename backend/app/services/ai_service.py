"""AI orchestration: provider resolution, prompt resolution & rendering, quota, fallback, usage ledger.

Every call — successful or failed — is written to ``ai_usage_events`` under an idempotency key,
so a retried pipeline step never bills twice. Costs come from the versioned platform price list.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.default_prompts import DEFAULT_PROMPTS
from app.ai.providers import AIProviderError, Completion, ProviderConfig, complete
from app.core.errors import NotFound, QuotaExceeded, ValidationFailed
from app.core.logging import get_logger
from app.models import (
    AIModelPrice,
    AIPrompt,
    AIPromptVersion,
    AIProvider,
    AIUsageEvent,
    PromptStatus,
    SystemSetting,
    TenantSetting,
)
from app.security.secrets import decrypt
from app.services import tenant_service

log = get_logger(__name__)
_VAR = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


class AINotConfigured(Exception):
    pass


@dataclass
class AIResult:
    data: dict[str, Any] | None
    text: str
    completion: Completion
    provider: AIProvider
    prompt_version: AIPromptVersion
    cost: Decimal | None
    credits: int


# ----------------------------------------------------------------- settings
def get_setting(db: Session, tenant_id: uuid.UUID, key: str, default: Any = None) -> Any:
    """Platform default → tenant override."""
    t = db.scalar(select(TenantSetting.value).where(TenantSetting.tenant_id == tenant_id, TenantSetting.key == key))
    if t is not None:
        return t
    s = db.scalar(select(SystemSetting.value).where(SystemSetting.key == key))
    return s if s is not None else default


# ---------------------------------------------------------------- providers
def active_provider(db: Session, tenant_id: uuid.UUID, provider_id: uuid.UUID | None = None) -> AIProvider | None:
    stmt = select(AIProvider).where(AIProvider.tenant_id == tenant_id, AIProvider.is_active.is_(True))
    if provider_id:
        return db.scalar(stmt.where(AIProvider.id == provider_id))
    return db.scalar(stmt.order_by(AIProvider.is_default.desc(), AIProvider.created_at).limit(1))


def provider_config(p: AIProvider, model: str | None = None) -> ProviderConfig:
    return ProviderConfig(
        kind=p.kind.value, api_key=decrypt(p.api_key_encrypted) if p.api_key_encrypted else None,
        model=model or p.default_model, base_url=p.base_url, api_version=p.api_version,
        temperature=p.temperature, max_tokens=p.max_tokens, timeout_seconds=p.timeout_seconds,
    )


# ------------------------------------------------------------------ prompts
def ensure_default_prompts(db: Session) -> None:
    """Create platform default prompts (published v1) if missing. Idempotent."""
    for spec in DEFAULT_PROMPTS:
        prompt = db.scalar(select(AIPrompt).where(AIPrompt.tenant_id.is_(None), AIPrompt.code == spec["code"]))
        if prompt is not None:
            continue
        prompt = AIPrompt(tenant_id=None, code=spec["code"], name=spec["name"], category=spec["category"],
                          description=spec["description"], published_version=1)
        prompt.versions.append(AIPromptVersion(
            tenant_id=None, version=1, status=PromptStatus.published, system_prompt=spec["system_prompt"],
            user_template=spec["user_template"], variables=spec["variables"], published_at=datetime.now(UTC),
            notes="Version plateforme initiale"))
        db.add(prompt)
    db.flush()


def resolve_prompt(db: Session, tenant_id: uuid.UUID, code: str) -> AIPromptVersion:
    """Tenant's published override if any, else the platform default."""
    for owner in (tenant_id, None):
        cond = AIPrompt.tenant_id.is_(None) if owner is None else AIPrompt.tenant_id == owner
        prompt = db.scalar(select(AIPrompt).where(cond, AIPrompt.code == code))
        if prompt is not None and prompt.published_version is not None:
            version = next((v for v in prompt.versions if v.version == prompt.published_version), None)
            if version is not None:
                return version
    raise NotFound(f"No published prompt for '{code}'")


def render(template: str, variables: dict[str, Any]) -> str:
    def sub(m: re.Match[str]) -> str:
        value = variables.get(m.group(1), "")
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return _VAR.sub(sub, template)


def neutralise(content: str, limit: int) -> str:
    """Keep the document inside its delimiters (no early closing tag) and bounded."""
    content = content.replace("</document>", "</ document>").replace("<document>", "< document>")
    return content[:limit]


def parse_json(text: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1] if "{" in cleaned else ""):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            continue
    return None


# -------------------------------------------------------------- usage/costs
def price_for(db: Session, kind: str, model: str, at: datetime) -> AIModelPrice | None:
    return db.scalar(select(AIModelPrice).where(AIModelPrice.provider_kind == kind, AIModelPrice.model == model,
                                                AIModelPrice.effective_from <= at)
                     .order_by(AIModelPrice.effective_from.desc()).limit(1))


def compute_cost(price: AIModelPrice | None, tin: int, tout: int) -> tuple[Decimal | None, int]:
    """1 credit = 0.001 USD of estimated cost; without a configured price, 1 credit per 1,000 tokens."""
    if price is None:
        return None, max(1, math.ceil((tin + tout) / 1000)) if (tin + tout) else 0
    cost = (Decimal(tin) * price.input_per_mtok + Decimal(tout) * price.output_per_mtok) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001")), max(1, math.ceil(cost * 1000))


def credits_used_this_month(db: Session, tenant_id: uuid.UUID) -> int:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(db.scalar(select(func.coalesce(func.sum(AIUsageEvent.credits), 0)).where(
        AIUsageEvent.tenant_id == tenant_id, AIUsageEvent.created_at >= start)) or 0)


def check_quota(db: Session, tenant_id: uuid.UUID) -> None:
    limit = tenant_service.get_quota(db, tenant_id, "ai_credits_monthly")
    if limit is not None and credits_used_this_month(db, tenant_id) >= limit:
        raise QuotaExceeded("Monthly AI credit quota reached for this organisation", code="ai_quota_exceeded",
                            details={"limit": limit})


def record_usage(db: Session, *, tenant_id: uuid.UUID, key: str, feature: str, provider: AIProvider, model: str,
                 prompt: AIPromptVersion | None, document_id: uuid.UUID | None, user_id: uuid.UUID | None,
                 completion: Completion | None, error: str | None) -> tuple[Decimal | None, int]:
    tin = completion.input_tokens if completion else 0
    tout = completion.output_tokens if completion else 0
    price = price_for(db, provider.kind.value, model, datetime.now(UTC))
    cost, credits = compute_cost(price, tin, tout)
    stmt = insert(AIUsageEvent).values(
        tenant_id=tenant_id, idempotency_key=key[:200], user_id=user_id, feature=feature, provider_id=provider.id,
        provider_kind=provider.kind.value, model=model, prompt_code=prompt.prompt.code if prompt else None,
        prompt_version=prompt.version if prompt else None, document_id=document_id,
        status="error" if error else "success", input_tokens=tin, output_tokens=tout,
        latency_ms=completion.latency_ms if completion else None, estimated_cost=cost,
        price_id=price.id if price else None, credits=credits, error=(error or None) and error[:1000],
    ).on_conflict_do_nothing(index_elements=["idempotency_key"])
    db.execute(stmt)
    return cost, credits


# --------------------------------------------------------------------- run
def run_prompt(db: Session, tenant_id: uuid.UUID, *, prompt_code: str | None = None,
               prompt_version: AIPromptVersion | None = None, variables: dict[str, Any], feature: str,
               idempotency_key: str, document_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None,
               provider_id: uuid.UUID | None = None, model: str | None = None) -> AIResult:
    provider = active_provider(db, tenant_id, provider_id)
    if provider is None:
        raise AINotConfigured("No active AI provider configured for this organisation")
    check_quota(db, tenant_id)
    version = prompt_version or resolve_prompt(db, tenant_id, prompt_code or "")
    system = render(version.system_prompt, variables)
    user = render(version.user_template, variables)
    json_mode = version.output_format == "json"

    chain = [provider]
    if provider.fallback_provider_id:
        fb = active_provider(db, tenant_id, provider.fallback_provider_id)
        if fb is not None and fb.id != provider.id:
            chain.append(fb)
    last_error: AIProviderError | None = None
    for i, current in enumerate(chain):
        used_model = model if (model and i == 0) else (version.model if i == 0 and version.model else current.default_model)
        key = f"{idempotency_key}:{current.id}"
        try:
            completion = complete(provider_config(current, used_model), system, user, json_mode=json_mode)
        except AIProviderError as exc:
            record_usage(db, tenant_id=tenant_id, key=key, feature=feature, provider=current, model=used_model,
                         prompt=version, document_id=document_id, user_id=user_id, completion=None, error=str(exc))
            log.warning("ai_provider_failed", extra={"provider": current.kind.value, "error": str(exc)})
            last_error = exc
            continue
        cost, credits = record_usage(db, tenant_id=tenant_id, key=key, feature=feature, provider=current,
                                     model=used_model, prompt=version, document_id=document_id, user_id=user_id,
                                     completion=completion, error=None)
        data = parse_json(completion.text) if json_mode else None
        return AIResult(data=data, text=completion.text, completion=completion, provider=current,
                        prompt_version=version, cost=cost, credits=credits)
    assert last_error is not None
    raise last_error


def build_document_content(pages: list[tuple[int, str]], limit: int) -> str:
    return neutralise("\n\n".join(f"[[page {n}]]\n{t}" for n, t in pages if t), limit)


def validate_prompt_template(system: str, user: str) -> list[str]:
    names = sorted(set(_VAR.findall(system)) | set(_VAR.findall(user)))
    if "document_content" in names and "<document>" not in user:
        raise ValidationFailed("{{document_content}} must stay inside <document>…</document> delimiters")
    return names
