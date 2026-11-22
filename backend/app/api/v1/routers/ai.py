"""AI administration: providers, Prompt Management Studio, consumption; document AI actions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.providers import AIProviderError, complete
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.database.session import get_db, set_session_tenant
from app.models import (
    AIModelPrice,
    AIPrompt,
    AIPromptTest,
    AIPromptVersion,
    AIProvider,
    AIUsageEvent,
    Document,
    PromptStatus,
)
from app.repositories.base import get_owned
from app.schemas.ai import (
    PriceIn,
    PriceOut,
    PromptOut,
    PromptTestIn,
    PromptTestOut,
    PromptVersionIn,
    PromptVersionOut,
    ProviderIn,
    ProviderOut,
)
from app.schemas.common import Message
from app.security.context import Principal, require, require_platform
from app.security.secrets import encrypt, hint
from app.services import ai_service, tenant_service
from app.workers.celery_app import enqueue_processing

router = APIRouter(tags=["AI"])
ADMIN = "tenant_settings:administer"


# --------------------------------------------------------------- providers
def _provider_out(p: AIProvider) -> ProviderOut:
    return ProviderOut.model_validate(p).model_copy(update={"api_key_set": bool(p.api_key_encrypted)})


def _apply_provider(db: Session, p: AIProvider, body: ProviderIn, tenant_id: uuid.UUID) -> None:
    data = body.model_dump(exclude={"api_key", "clear_api_key", "base_url"})
    for k, v in data.items():
        setattr(p, k, v)
    p.base_url = str(body.base_url).rstrip("/") if body.base_url else None
    if body.clear_api_key:
        p.api_key_encrypted, p.api_key_hint = None, None
    elif body.api_key:
        p.api_key_encrypted, p.api_key_hint = encrypt(body.api_key.strip()), hint(body.api_key.strip())
    if body.kind in ("openai", "anthropic", "gemini", "azure_openai") and not p.api_key_encrypted:
        raise ValidationFailed("An API key is required for this provider")
    if body.kind in ("azure_openai", "openai_compatible") and not p.base_url:
        raise ValidationFailed("A base URL / endpoint is required for this provider")
    if body.fallback_provider_id:
        fb = get_owned(db, AIProvider, tenant_id, body.fallback_provider_id, label="Fallback provider")
        if fb.id == p.id:
            raise ValidationFailed("A provider cannot be its own fallback")
    if body.is_default:
        for other in db.scalars(select(AIProvider).where(AIProvider.tenant_id == tenant_id,
                                                         AIProvider.is_default.is_(True))):
            if other.id != p.id:
                other.is_default = False
        db.flush()


@router.get("/ai/providers", response_model=list[ProviderOut])
def list_providers(p: Principal = Depends(require("prompt:read")), db: Session = Depends(get_db)) -> list:
    rows = db.scalars(select(AIProvider).where(AIProvider.tenant_id == p.tenant_id).order_by(AIProvider.name))
    return [_provider_out(x) for x in rows]


@router.post("/ai/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderIn, p: Principal = Depends(require(ADMIN)), db: Session = Depends(get_db)) -> ProviderOut:
    if db.scalar(select(AIProvider.id).where(AIProvider.tenant_id == p.tenant_id, AIProvider.name == body.name)):
        raise Conflict("A provider with this name already exists")
    prov = AIProvider(tenant_id=p.tenant_id, name=body.name, kind=body.kind, default_model=body.default_model)
    _apply_provider(db, prov, body, p.tenant_id)
    if not db.scalar(select(AIProvider.id).where(AIProvider.tenant_id == p.tenant_id)):
        prov.is_default = True  # the first provider becomes the default
    db.add(prov)
    db.flush()
    p.audit(db, "ai.provider_created", resource_type="ai_provider", resource_id=prov.id,
            details={"kind": prov.kind.value, "model": prov.default_model})
    return _provider_out(prov)


@router.put("/ai/providers/{provider_id}", response_model=ProviderOut)
def update_provider(provider_id: uuid.UUID, body: ProviderIn, p: Principal = Depends(require(ADMIN)),
                    db: Session = Depends(get_db)) -> ProviderOut:
    prov = get_owned(db, AIProvider, p.tenant_id, provider_id, label="Provider")
    _apply_provider(db, prov, body, p.tenant_id)
    db.flush()
    p.audit(db, "ai.provider_updated", resource_type="ai_provider", resource_id=prov.id,
            details={"key_rotated": bool(body.api_key), "model": prov.default_model, "active": prov.is_active})
    return _provider_out(prov)


@router.delete("/ai/providers/{provider_id}", response_model=Message)
def delete_provider(provider_id: uuid.UUID, p: Principal = Depends(require(ADMIN)), db: Session = Depends(get_db)) -> Message:
    prov = get_owned(db, AIProvider, p.tenant_id, provider_id, label="Provider")
    db.delete(prov)
    p.audit(db, "ai.provider_deleted", resource_type="ai_provider", resource_id=provider_id)
    return Message(message="Provider deleted")


@router.post("/ai/providers/{provider_id}/test", response_model=ProviderOut)
def test_provider(provider_id: uuid.UUID, p: Principal = Depends(require(ADMIN)), db: Session = Depends(get_db)) -> ProviderOut:
    """Real round-trip to the provider with a tiny prompt (counted in the consumption ledger)."""
    prov = get_owned(db, AIProvider, p.tenant_id, provider_id, label="Provider")
    ai_service.check_quota(db, p.tenant_id)
    cfg = ai_service.provider_config(prov)
    cfg.max_tokens = 64
    completion, error = None, None
    try:
        completion = complete(cfg, "Réponds uniquement avec un objet JSON.", 'Renvoie exactement {"status": "ok"}.')
        data = ai_service.parse_json(completion.text)
        message = f"Connexion réussie ({completion.model}, {completion.latency_ms} ms)" + (
            "" if data else " — réponse non JSON")
    except AIProviderError as exc:
        error, message = str(exc), str(exc)[:1000]
    ai_service.record_usage(db, tenant_id=p.tenant_id, key=f"provider_test:{prov.id}:{uuid.uuid4()}",
                            feature="connection_test", provider=prov, model=cfg.model, prompt=None, document_id=None,
                            user_id=p.user.id, completion=completion, error=error)
    prov.last_test_at, prov.last_test_ok, prov.last_test_message = datetime.now(UTC), error is None, message
    db.flush()
    p.audit(db, "ai.provider_tested", resource_type="ai_provider", resource_id=prov.id, outcome="success" if not error else "failure")
    return _provider_out(prov)


# ----------------------------------------------------------------- prompts
def _prompt_out(db: Session, prompt: AIPrompt, tenant_id: uuid.UUID) -> PromptOut:
    try:
        effective = ai_service.resolve_prompt(db, tenant_id, prompt.code).prompt_id == prompt.id
    except NotFound:
        effective = False
    return PromptOut(id=prompt.id, code=prompt.code, name=prompt.name, description=prompt.description,
                     category=prompt.category, scope="platform" if prompt.tenant_id is None else "tenant",
                     published_version=prompt.published_version, effective=effective,
                     versions=[PromptVersionOut.model_validate(v) for v in prompt.versions])


@router.get("/ai/prompts", response_model=list[PromptOut])
def list_prompts(p: Principal = Depends(require("prompt:read")), db: Session = Depends(get_db)) -> list[PromptOut]:
    rows = db.scalars(select(AIPrompt).where((AIPrompt.tenant_id.is_(None)) | (AIPrompt.tenant_id == p.tenant_id))
                      .order_by(AIPrompt.code, AIPrompt.tenant_id.nulls_first()))
    return [_prompt_out(db, x, p.tenant_id) for x in rows]


@router.post("/ai/prompts/{code}/versions", response_model=PromptOut, status_code=201)
def create_version(code: str, body: PromptVersionIn, p: Principal = Depends(require("prompt:create")),
                   db: Session = Depends(get_db)) -> PromptOut:
    variables = ai_service.validate_prompt_template(body.system_prompt, body.user_template)
    prompt = db.scalar(select(AIPrompt).where(AIPrompt.tenant_id == p.tenant_id, AIPrompt.code == code))
    if prompt is None:
        base = db.scalar(select(AIPrompt).where(AIPrompt.tenant_id.is_(None), AIPrompt.code == code))
        if base is None:
            raise NotFound("Unknown prompt")
        prompt = AIPrompt(tenant_id=p.tenant_id, code=code, name=base.name, category=base.category,
                          description=base.description, published_version=None)
        db.add(prompt)
        db.flush()
    number = max((v.version for v in prompt.versions), default=0) + 1
    version = AIPromptVersion(prompt_id=prompt.id, tenant_id=p.tenant_id, version=number, status=PromptStatus.draft,
                              system_prompt=body.system_prompt, user_template=body.user_template,
                              variables=variables, model=body.model, notes=body.notes, created_by=p.user.id)
    db.add(version)
    db.flush()
    db.refresh(prompt)
    p.audit(db, "ai.prompt_version_created", resource_type="ai_prompt", resource_id=prompt.id,
            details={"code": code, "version": number})
    return _prompt_out(db, prompt, p.tenant_id)


@router.post("/ai/prompts/versions/{version_id}/publish", response_model=PromptOut)
def publish_version(version_id: uuid.UUID, force: bool = False, p: Principal = Depends(require("prompt:administer")),
                    db: Session = Depends(get_db)) -> PromptOut:
    version = db.scalar(select(AIPromptVersion).where(AIPromptVersion.id == version_id,
                                                      AIPromptVersion.tenant_id == p.tenant_id))
    if version is None:
        raise NotFound("Prompt version not found (platform versions cannot be published by a tenant)")
    tested = db.scalar(select(func.count()).select_from(AIPromptTest).where(
        AIPromptTest.prompt_version_id == version.id, AIPromptTest.ok.is_(True)))
    if not tested and not force:
        raise ValidationFailed("Test this version successfully before publishing it (or publish with force)",
                               code="prompt_not_tested")
    prompt = version.prompt
    for v in prompt.versions:
        if v.status == PromptStatus.published and v.id != version.id:
            v.status = PromptStatus.archived
    version.status, version.published_at = PromptStatus.published, datetime.now(UTC)
    prompt.published_version = version.version
    db.flush()
    p.audit(db, "ai.prompt_published", resource_type="ai_prompt", resource_id=prompt.id,
            details={"code": prompt.code, "version": version.version, "forced_without_test": bool(force and not tested)})
    return _prompt_out(db, prompt, p.tenant_id)


@router.post("/ai/prompts/{prompt_id}/reset", response_model=PromptOut)
def reset_to_platform(prompt_id: uuid.UUID, p: Principal = Depends(require("prompt:administer")),
                      db: Session = Depends(get_db)) -> PromptOut:
    prompt = db.scalar(select(AIPrompt).where(AIPrompt.id == prompt_id, AIPrompt.tenant_id == p.tenant_id))
    if prompt is None:
        raise NotFound("Prompt not found")
    for v in prompt.versions:
        if v.status == PromptStatus.published:
            v.status = PromptStatus.archived
    prompt.published_version = None
    db.flush()
    p.audit(db, "ai.prompt_reset_to_platform", resource_type="ai_prompt", resource_id=prompt.id)
    return _prompt_out(db, prompt, p.tenant_id)


@router.post("/ai/prompts/test", response_model=PromptTestOut)
def test_prompt(body: PromptTestIn, p: Principal = Depends(require("prompt:update", "document:read")),
                db: Session = Depends(get_db)) -> PromptTestOut:
    from app.ai.document_ai import all_variables

    version = db.scalar(select(AIPromptVersion).where(
        AIPromptVersion.id == body.version_id,
        (AIPromptVersion.tenant_id.is_(None)) | (AIPromptVersion.tenant_id == p.tenant_id)))
    if version is None:
        raise NotFound("Prompt version not found")
    doc = get_owned(db, Document, p.tenant_id, body.document_id, label="Document")
    test = AIPromptTest(tenant_id=p.tenant_id, prompt_version_id=version.id, document_id=doc.id,
                        provider_id=body.provider_id, created_by=p.user.id)
    credits = None
    provider_name = None
    try:
        result = ai_service.run_prompt(db, p.tenant_id, prompt_version=version, variables=all_variables(db, doc),
                                       feature="prompt_test", idempotency_key=f"prompt_test:{uuid.uuid4()}",
                                       document_id=doc.id, user_id=p.user.id, provider_id=body.provider_id,
                                       model=body.model)
        c = result.completion
        test.provider_id, test.model, test.output_text = result.provider.id, c.model, c.text[:50000]
        test.parsed, test.ok = result.data, result.data is not None or version.output_format != "json"
        test.input_tokens, test.output_tokens, test.latency_ms = c.input_tokens, c.output_tokens, c.latency_ms
        test.estimated_cost, credits, provider_name = result.cost, result.credits, result.provider.name
        if not test.ok:
            test.error = "The response is not valid JSON"
    except ai_service.AINotConfigured as exc:
        raise ValidationFailed(str(exc), code="ai_not_configured") from exc
    except AIProviderError as exc:
        test.ok, test.error = False, str(exc)[:4000]
    db.add(test)
    db.flush()
    return PromptTestOut(id=test.id, ok=test.ok, parsed=test.parsed, output_text=test.output_text, error=test.error,
                         model=test.model, provider=provider_name, input_tokens=test.input_tokens,
                         output_tokens=test.output_tokens, latency_ms=test.latency_ms,
                         estimated_cost=test.estimated_cost, credits=credits, created_at=test.created_at or datetime.now(UTC))


@router.get("/ai/prompts/versions/{version_id}/tests", response_model=list[PromptTestOut])
def version_tests(version_id: uuid.UUID, p: Principal = Depends(require("prompt:read")),
                  db: Session = Depends(get_db)) -> list[PromptTestOut]:
    rows = db.scalars(select(AIPromptTest).where(AIPromptTest.prompt_version_id == version_id,
                                                 AIPromptTest.tenant_id == p.tenant_id)
                      .order_by(AIPromptTest.created_at.desc()).limit(20))
    return [PromptTestOut(id=t.id, ok=t.ok, parsed=t.parsed, output_text=t.output_text, error=t.error, model=t.model,
                          provider=None, input_tokens=t.input_tokens, output_tokens=t.output_tokens,
                          latency_ms=t.latency_ms, estimated_cost=t.estimated_cost, credits=None,
                          created_at=t.created_at) for t in rows]


# ------------------------------------------------------------------- usage
@router.get("/ai/usage")
def usage(p: Principal = Depends(require("report:read")), db: Session = Depends(get_db),
          days: int = Query(30, ge=1, le=366)) -> dict:
    tid = p.tenant_id
    since = datetime.now(UTC) - timedelta(days=days - 1)
    base = (AIUsageEvent.tenant_id == tid, AIUsageEvent.created_at >= since)

    def grouped(col):  # type: ignore[no-untyped-def]
        rows = db.execute(select(col, func.count(), func.sum(AIUsageEvent.credits),
                                 func.sum(AIUsageEvent.input_tokens + AIUsageEvent.output_tokens),
                                 func.sum(AIUsageEvent.estimated_cost))
                          .where(*base).group_by(col).order_by(func.sum(AIUsageEvent.credits).desc())).all()
        return [{"key": k, "calls": int(n), "credits": int(c or 0), "tokens": int(t or 0),
                 "cost": float(cost) if cost is not None else None} for k, n, c, t, cost in rows]

    day = func.date_trunc("day", AIUsageEvent.created_at)
    per_day = {d.date(): int(c or 0) for d, c in db.execute(
        select(day, func.sum(AIUsageEvent.credits)).where(*base).group_by(day)).all()}
    totals = db.execute(select(func.count(), func.coalesce(func.sum(AIUsageEvent.credits), 0),
                               func.coalesce(func.sum(AIUsageEvent.input_tokens), 0),
                               func.coalesce(func.sum(AIUsageEvent.output_tokens), 0),
                               func.sum(AIUsageEvent.estimated_cost),
                               func.count().filter(AIUsageEvent.status == "error"),
                               func.avg(AIUsageEvent.latency_ms)).where(*base)).one()
    return {
        "period_days": days,
        "credits_used_month": ai_service.credits_used_this_month(db, tid),
        "credits_limit_month": tenant_service.get_quota(db, tid, "ai_credits_monthly"),
        "totals": {"calls": int(totals[0]), "credits": int(totals[1]), "input_tokens": int(totals[2]),
                   "output_tokens": int(totals[3]), "cost": float(totals[4]) if totals[4] is not None else None,
                   "errors": int(totals[5]), "avg_latency_ms": int(totals[6]) if totals[6] else None},
        "by_feature": grouped(AIUsageEvent.feature),
        "by_model": grouped(AIUsageEvent.model),
        "per_day": [{"date": (since + timedelta(days=i)).date().isoformat(),
                     "credits": per_day.get((since + timedelta(days=i)).date(), 0)} for i in range(days)],
    }


# ------------------------------------------------------------------ prices
@router.get("/ai/prices", response_model=list[PriceOut])
def list_prices(_: Principal = Depends(require("prompt:read")), db: Session = Depends(get_db)) -> list:
    return list(db.scalars(select(AIModelPrice).order_by(AIModelPrice.provider_kind, AIModelPrice.model,
                                                         AIModelPrice.effective_from.desc())))


@router.post("/platform/ai/prices", response_model=PriceOut, status_code=201)
def add_price(body: PriceIn, p: Principal = Depends(require_platform("platform:administer")),
              db: Session = Depends(get_db)) -> AIModelPrice:
    set_session_tenant(db, None, bypass_rls=True)
    price = AIModelPrice(provider_kind=body.provider_kind.value, model=body.model, input_per_mtok=body.input_per_mtok,
                         output_per_mtok=body.output_per_mtok, effective_from=body.effective_from or datetime.now(UTC))
    db.add(price)
    db.flush()
    p.audit(db, "platform.ai_price_added", tenant_id=None, resource_type="ai_model_price", resource_id=price.id,
            details=body.model_dump(mode="json"))
    return price


# --------------------------------------------------------- document actions
@router.post("/documents/{document_id}/ai/analyze", response_model=Message)
def analyze_document(document_id: uuid.UUID, p: Principal = Depends(require("metadata:update")),
                     db: Session = Depends(get_db)) -> Message:
    doc = get_owned(db, Document, p.tenant_id, document_id, label="Document")
    if ai_service.active_provider(db, p.tenant_id) is None:
        raise ValidationFailed("No active AI provider configured", code="ai_not_configured")
    p.audit(db, "document.ai_analysis_requested", resource_type="document", resource_id=doc.id)
    db.commit()
    enqueue_processing(p.tenant_id, doc.id, force=True, priority=True,
                       only_steps=["classification", "metadata_extraction", "publication"])
    return Message(message="AI analysis queued")


@router.post("/documents/{document_id}/ai/summary")
def summarize_document(document_id: uuid.UUID, p: Principal = Depends(require("document:read", "ai_assistant:read")),
                       db: Session = Depends(get_db)) -> dict:
    from app.ai.document_ai import summarize

    doc = get_owned(db, Document, p.tenant_id, document_id, label="Document")
    try:
        out = summarize(db, doc, user_id=p.user.id)
    except ai_service.AINotConfigured as exc:
        raise ValidationFailed(str(exc), code="ai_not_configured") from exc
    except AIProviderError as exc:
        raise ValidationFailed(f"AI provider error: {exc}", code="ai_provider_error") from exc
    p.audit(db, "document.ai_summary", resource_type="document", resource_id=doc.id, details={"credits": out["credits"]})
    return out
