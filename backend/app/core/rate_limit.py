"""Fixed-window rate limiter backed by Redis, with an in-process fallback.

The fallback keeps the platform usable when Redis is briefly unavailable,
but production deployments should always have Redis.
"""

from __future__ import annotations

import threading
import time

from app.core.config import get_settings
from app.core.errors import RateLimited
from app.core.logging import get_logger

log = get_logger(__name__)

_local: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()
_redis = None
_redis_failed_at = 0.0


def _get_redis():  # type: ignore[no-untyped-def]
    global _redis, _redis_failed_at
    if _redis is None and time.time() - _redis_failed_at > 30:
        try:
            import redis

            client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.5)
            client.ping()
            _redis = client
        except Exception:  # noqa: BLE001
            _redis_failed_at = time.time()
            log.warning("rate_limit_redis_unavailable")
    return _redis


def hit(key: str, limit: int, window_seconds: int = 60) -> None:
    """Count one hit; raise RateLimited when the window's limit is exceeded."""
    window = int(time.time() // window_seconds)
    bucket = f"rl:{key}:{window}"
    client = _get_redis()
    count: int
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window_seconds + 1)
            count = int(pipe.execute()[0])
        except Exception:  # noqa: BLE001
            client = None
    if client is None:
        with _lock:
            current, expires = _local.get(bucket, (0, time.time() + window_seconds))
            count = current + 1
            _local[bucket] = (count, expires)
            for k in [k for k, (_, exp) in _local.items() if exp < time.time()]:
                _local.pop(k, None)
    if count > limit:
        raise RateLimited("Too many attempts, please retry later", details={"retry_after_s": window_seconds})


def reset_local() -> None:
    with _lock:
        _local.clear()
