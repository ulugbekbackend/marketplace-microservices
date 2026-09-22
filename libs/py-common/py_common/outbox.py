"""Transactional outbox: the business change and the event row commit together, a worker
publishes them afterwards. Storage is service specific, this module holds the shared parts."""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from contracts.events import EventEnvelope

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PendingEvent:
    """One unpublished outbox row, already shaped as an envelope."""

    id: int | UUID
    envelope: EventEnvelope


class Publisher(Protocol):
    def publish(self, envelope: EventEnvelope) -> None:
        """Send one event and wait for the broker to confirm it."""
        ...


class OutboxStore(Protocol):
    def fetch_unpublished(self, limit: int) -> Sequence[PendingEvent]:
        """Lock and return unpublished rows (SELECT ... FOR UPDATE SKIP LOCKED)."""
        ...

    def mark_published(self, ids: Iterable[int | UUID]) -> None: ...


def publish_pending(store: OutboxStore, publisher: Publisher, *, limit: int = 100) -> int:
    """Publish one batch of outbox rows. Returns how many were confirmed.

    A row is marked published only after the broker confirmed it, so a crash means a
    duplicate delivery, never a lost event. Consumers are idempotent by event_id.
    """
    pending = store.fetch_unpublished(limit)
    published: list[int | UUID] = []
    for row in pending:
        try:
            publisher.publish(row.envelope)
        except Exception:
            logger.exception(
                "outbox publish failed", extra={"event_id": str(row.envelope.event_id)}
            )
            break
        published.append(row.id)

    if published:
        store.mark_published(published)
    return len(published)
