"""Provider adapters. Each one turns (system, user) into a completion with token usage.

Raw HTTP (httpx) keeps the engine vendor-neutral and free of SDK lock-in. Retries with
exponential backoff on 408/409/429/5xx and network errors; authentication and validation
errors are surfaced immediately.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

ANTHROPIC_VERSION = "2026-10-21"
AZURE_DEFAULT_API_VERSION = "2024-10-21"

# Tests inject an httpx.MockTransport here; production uses the real network.
transport: httpx.BaseTransport | None = None


class AIProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


@dataclass
class ProviderConfig:
    kind: str
    api_key: str | None
    model: str
    base_url: str | None = None
    api_version: str | None = None
    temperature: float | None = None
    max_tokens: int = 2048
    timeout_seconds: int = 60


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str


def _request(cfg: ProviderConfig, system: str, user: str, json_mode: bool) -> tuple[str, dict, dict]:
    """Return (url, headers, body) for the provider."""
    if cfg.kind in ("openai", "openai_compatible"):
        base = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
        body: dict = {"model": cfg.model, "messages": [{"role": "system", "content": system},
                                                        {"role": "user", "content": user}]}
        body["max_completion_tokens" if cfg.kind == "openai" else "max_tokens"] = cfg.max_tokens
        if cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return f"{base}/chat/completions", headers, body
    if cfg.kind == "azure_openai":
        if not cfg.base_url:
            raise AIProviderError("Azure OpenAI requires the resource endpoint (base URL)")
        version = cfg.api_version or AZURE_DEFAULT_API_VERSION
        url = f"{cfg.base_url.rstrip('/')}/openai/deployments/{cfg.model}/chat/completions?api-version={version}"
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": cfg.max_tokens}
        if cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return url, {"api-key": cfg.api_key or ""}, body
    if cfg.kind == "anthropic":
        base = (cfg.base_url or "https://api.anthropic.com").rstrip("/")
        body = {"model": cfg.model, "system": system, "max_tokens": cfg.max_tokens,
                "messages": [{"role": "user", "content": user}]}
        if cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        return f"{base}/v1/messages", {"x-api-key": cfg.api_key or "", "anthropic-version": ANTHROPIC_VERSION}, body
    if cfg.kind == "gemini":
        base = (cfg.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        gen: dict = {"maxOutputTokens": cfg.max_tokens}
        if cfg.temperature is not None:
            gen["temperature"] = cfg.temperature
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gen}
        return f"{base}/models/{cfg.model}:generateContent", {"x-goog-api-key": cfg.api_key or ""}, body
    raise AIProviderError(f"Unknown provider kind '{cfg.kind}'")


def _parse(cfg: ProviderConfig, data: dict) -> tuple[str, int, int, str]:
    try:
        if cfg.kind in ("openai", "openai_compatible", "azure_openai"):
            usage = data.get("usage") or {}
            return (data["choices"][0]["message"].get("content") or "", int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)), data.get("model", cfg.model))
        if cfg.kind == "anthropic":
            usage = data.get("usage") or {}
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)), data.get("model", cfg.model)
        if cfg.kind == "gemini":
            usage = data.get("usageMetadata") or {}
            parts = data["candidates"][0]["content"].get("parts", [])
            return ("".join(p.get("text", "") for p in parts), int(usage.get("promptTokenCount", 0)),
                    int(usage.get("candidatesTokenCount", 0)), data.get("modelVersion", cfg.model))
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError(f"Unexpected response format from {cfg.kind}") from exc
    raise AIProviderError(f"Unknown provider kind '{cfg.kind}'")


def complete(cfg: ProviderConfig, system: str, user: str, *, json_mode: bool = True) -> Completion:
    settings = get_settings()
    url, headers, body = _request(cfg, system, user, json_mode)
    last: AIProviderError | None = None
    for attempt in range(settings.ai_max_retries):
        if attempt:
            time.sleep(settings.ai_retry_base_seconds * (2 ** (attempt - 1)))
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=cfg.timeout_seconds, transport=transport) as client:
                resp = client.post(url, headers={**headers, "content-type": "application/json"}, json=body)
        except httpx.TimeoutException:
            last = AIProviderError("Provider timeout", retryable=True)
            continue
        except httpx.HTTPError as exc:
            last = AIProviderError(f"Network error: {exc}", retryable=True)
            continue
        latency = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            detail = resp.text[:300]
            retryable = resp.status_code in (408, 409, 429) or resp.status_code >= 500
            last = AIProviderError(f"{cfg.kind} HTTP {resp.status_code}: {detail}", retryable=retryable,
                                   status=resp.status_code)
            if retryable:
                continue
            raise last
        text, tin, tout, model = _parse(cfg, resp.json())
        return Completion(text=text, input_tokens=tin, output_tokens=tout, latency_ms=latency, model=model)
    assert last is not None
    raise last
