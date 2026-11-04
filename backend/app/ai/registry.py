"""AI provider registry (placeholder for Phase 3).

Phase 3 introduces ``ai_providers`` / ``ai_models`` / ``ai_configurations``
tables and provider adapters (OpenAI, Azure OpenAI, Anthropic, Gemini, local
models). Until then no provider is configured and the pipeline reports the AI
steps as ``not_configured`` — nothing is simulated.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session


def get_active_provider(db: Session, tenant_id: uuid.UUID) -> None:
    return None
