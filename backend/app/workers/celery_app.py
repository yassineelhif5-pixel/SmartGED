"""Celery application: priority queues, retries with backoff, dead-letter handling."""

from __future__ import annotations

import uuid

from celery import Celery
from kombu import Queue

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
log = get_logger(__name__)

celery_app = Celery("documind", broker=settings.broker_url, backend=settings.result_backend)
celery_app.conf.update(
    task_always_eager=settings.celery_eager,
    task_eager_propagates=False,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    task_default_queue="documents",
    task_queues=(Queue("documents"), Queue("documents_priority"), Queue("dead_letter")),
    task_routes={"documind.process_document": {"queue": "documents"}},
    broker_transport_options={"visibility_timeout": 60 * 60},
    result_expires=60 * 60 * 24,
)


@celery_app.on_after_configure.connect
def _setup(**_: object) -> None:
    configure_logging()


@celery_app.task(name="documind.process_document", bind=True, max_retries=3, acks_late=True)
def process_document(self, tenant_id: str, document_id: str, force: bool = False) -> dict:  # type: ignore[no-untyped-def]
    from app.workers.pipeline import run_pipeline

    try:
        return run_pipeline(uuid.UUID(tenant_id), uuid.UUID(document_id), force=force)
    except Exception as exc:  # infrastructure failure (DB down, storage unreachable…)
        if self.request.retries >= self.max_retries:
            dead_letter.apply_async(args=[tenant_id, document_id, repr(exc)], queue="dead_letter")
            raise
        raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 2)) from exc


@celery_app.task(name="documind.dead_letter")
def dead_letter(tenant_id: str, document_id: str, error: str) -> None:
    log.error("pipeline_dead_letter", extra={"tenant_id": tenant_id, "document_id": document_id, "error": error})


def enqueue_processing(tenant_id: uuid.UUID, document_id: uuid.UUID, *, force: bool = False, priority: bool = False) -> None:
    process_document.apply_async(
        args=[str(tenant_id), str(document_id), force],
        queue="documents_priority" if priority else "documents",
    )
