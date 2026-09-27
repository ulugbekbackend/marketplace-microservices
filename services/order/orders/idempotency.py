"""Idempotency-Key handling for unsafe endpoints (checkout).

Per user and key, Redis keeps the final response and a hash of the request body for
``IDEMPOTENCY_TTL_SECONDS``:

    order:idem:{user_id}:{key}        {"hash", "status", "body"}   the stored response
    order:idem:{user_id}:{key}:lock   SET NX while the first request runs

Same key and body replay the stored response; another body gets 409
IDEMPOTENCY_KEY_REUSED; a request racing the first one gets 409 IDEMPOTENCY_IN_PROGRESS.
Only successful responses are stored: a failure changed nothing, so a retry with the
same key runs again (the cart may have been fixed in the meantime).
"""

import contextlib
import hashlib
import json
from collections.abc import Callable
from functools import lru_cache
from typing import Any
from uuid import UUID

import redis
from django.conf import settings
from rest_framework.response import Response

from contracts.headers import IDEMPOTENCY_KEY
from orders.clients import ServiceUnavailable
from py_common.web.drf import ApiError

KEY_PREFIX = "order:idem:"
MAX_KEY_LENGTH = 255
REPLAY_HEADER = "Idempotent-Replayed"


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(
        settings.REDIS_URL, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
    )


def request_hash(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def require_key(raw: str | None) -> str:
    key = (raw or "").strip()
    if not key:
        raise ApiError(
            "IDEMPOTENCY_KEY_REQUIRED", f"The {IDEMPOTENCY_KEY} header is required.", status=400
        )
    if len(key) > MAX_KEY_LENGTH:
        raise ApiError(
            "IDEMPOTENCY_KEY_INVALID",
            f"The {IDEMPOTENCY_KEY} header must not be longer than {MAX_KEY_LENGTH} characters.",
            status=400,
        )
    return key


def run_once(user_id: UUID, key: str, data: Any, handler: Callable[[], Response]) -> Response:
    """Run ``handler`` once per (user, key); later calls with the same body replay it."""
    storage_key = f"{KEY_PREFIX}{user_id}:{key}"
    lock_key = f"{storage_key}:lock"
    body_hash = request_hash(data)
    client = get_redis()
    try:
        stored = client.get(storage_key)
        if stored is not None:
            return _replay(stored, body_hash)
        if not client.set(lock_key, body_hash, nx=True, ex=settings.IDEMPOTENCY_LOCK_SECONDS):
            raise ApiError(
                "IDEMPOTENCY_IN_PROGRESS",
                "A request with this idempotency key is still being processed.",
                status=409,
            )
    except redis.RedisError as exc:
        raise ServiceUnavailable("redis") from exc

    try:
        # The first request may have finished between the read and the lock.
        stored = client.get(storage_key)
        if stored is not None:
            return _replay(stored, body_hash)
        response = handler()
        if 200 <= response.status_code < 300:
            record = {"hash": body_hash, "status": response.status_code, "body": response.data}
            client.set(
                storage_key,
                json.dumps(record, default=str),
                ex=settings.IDEMPOTENCY_TTL_SECONDS,
            )
        return response
    finally:
        # If Redis went away, the lock expires on its own.
        with contextlib.suppress(redis.RedisError):
            client.delete(lock_key)


def _replay(stored: str | bytes, body_hash: str) -> Response:
    record = json.loads(stored)
    if record["hash"] != body_hash:
        raise ApiError(
            "IDEMPOTENCY_KEY_REUSED",
            "This idempotency key was already used with a different request body.",
            status=409,
        )
    response = Response(record["body"], status=record["status"])
    response[REPLAY_HEADER] = "true"
    return response
