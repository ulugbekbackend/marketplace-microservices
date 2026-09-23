"""Writing to and reading from the outbox table."""

from collections.abc import Iterable, Sequence
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from contracts.events import EventEnvelope
from messaging.models import Outbox, ProcessedEvent
from py_common.outbox import PendingEvent


class OutsideTransactionError(RuntimeError):
    """An outbox row must share the transaction of the change it describes."""


def add_to_outbox(envelope: EventEnvelope) -> Outbox:
    """Store an event in the current transaction. Refuses to run in autocommit mode."""
    if not transaction.get_connection().in_atomic_block:
        raise OutsideTransactionError("add_to_outbox() must be called inside transaction.atomic")
    return Outbox.objects.create(
        event_id=envelope.event_id,
        event_type=envelope.event_type.value,
        correlation_id=envelope.correlation_id,
        occurred_at=envelope.occurred_at,
        version=envelope.version,
        payload=envelope.payload,
    )


def to_envelope(row: Outbox, *, producer: str = "catalog") -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": row.event_id,
            "event_type": row.event_type,
            "occurred_at": row.occurred_at,
            "producer": producer,
            "correlation_id": row.correlation_id,
            "version": row.version,
            "payload": row.payload,
        }
    )


class DjangoOutboxStore:
    """``py_common.outbox.OutboxStore`` on top of the Outbox table.

    Call ``fetch_unpublished`` and ``mark_published`` inside one transaction so the
    row locks hold until the batch is stamped.
    """

    def fetch_unpublished(self, limit: int) -> Sequence[PendingEvent]:
        rows = (
            Outbox.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True)
            .order_by("id")[:limit]
        )
        return [PendingEvent(id=row.id, envelope=to_envelope(row)) for row in rows]

    def mark_published(self, ids: Iterable[int | UUID]) -> None:
        Outbox.objects.filter(id__in=list(ids)).update(published_at=timezone.now())


def mark_processed(envelope: EventEnvelope) -> bool:
    """Record a consumed event in the current transaction.

    Returns False when the event was processed before. A concurrent duplicate blocks on
    the primary key until the first transaction ends, then sees the conflict.
    """
    if not transaction.get_connection().in_atomic_block:
        raise OutsideTransactionError("mark_processed() must be called inside transaction.atomic")
    _, created = ProcessedEvent.objects.get_or_create(
        event_id=envelope.event_id,
        defaults={"event_type": envelope.event_type.value},
    )
    return created
