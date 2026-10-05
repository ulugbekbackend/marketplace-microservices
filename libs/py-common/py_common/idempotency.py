"""Consumers must see each event once. Services with a database use a processed_events
table instead; this module is the Redis and in-memory variant."""

from typing import Protocol
from uuid import UUID

DEFAULT_TTL_SECONDS = 7 * 24 * 3600


class IdempotencyStore(Protocol):
    async def mark_processed(self, event_id: UUID) -> bool:
        """Return True when this event was seen for the first time."""
        ...

    async def release(self, event_id: UUID) -> None:
        """Forget an event whose handler failed, so its redelivery is processed."""
        ...


class MemoryIdempotencyStore:
    """For tests and single process workers."""

    def __init__(self) -> None:
        self._seen: set[UUID] = set()

    async def mark_processed(self, event_id: UUID) -> bool:
        if event_id in self._seen:
            return False
        self._seen.add(event_id)
        return True

    async def release(self, event_id: UUID) -> None:
        self._seen.discard(event_id)


class RedisIdempotencyStore:
    """SET NX with a TTL: the first writer wins, later duplicates are dropped."""

    def __init__(self, redis: object, *, prefix: str, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl_seconds

    def _key(self, event_id: UUID) -> str:
        return f"{self._prefix}:processed:{event_id}"

    async def mark_processed(self, event_id: UUID) -> bool:
        created = await self._redis.set(self._key(event_id), "1", nx=True, ex=self._ttl)  # type: ignore[attr-defined]
        return bool(created)

    async def release(self, event_id: UUID) -> None:
        await self._redis.delete(self._key(event_id))  # type: ignore[attr-defined]
