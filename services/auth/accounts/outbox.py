"""Publishing the auth outbox: the relay reads rows written by ``accounts.sellers``."""

from collections.abc import Iterable, Sequence
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from accounts.models import Outbox
from contracts.events import EventEnvelope
from py_common.outbox import PendingEvent, Publisher, publish_pending


class AuthOutboxStore:
    """``py_common.outbox.OutboxStore`` on top of ``accounts.Outbox``.

    Rows hold the whole envelope as JSON and use time ordered (UUIDv7) ids, so id order
    is write order. Call both methods inside one transaction so the row locks hold until
    the batch is stamped.
    """

    def fetch_unpublished(self, limit: int) -> Sequence[PendingEvent]:
        rows = (
            Outbox.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True)
            .order_by("id")[:limit]
        )
        return [
            PendingEvent(id=row.id, envelope=EventEnvelope.model_validate(row.payload))
            for row in rows
        ]

    def mark_published(self, ids: Iterable[int | UUID]) -> None:
        Outbox.objects.filter(id__in=list(ids)).update(published_at=timezone.now())


def relay_batch(publisher: Publisher, *, limit: int = 100) -> int:
    """Publish one batch of pending rows; the row locks hold until they are stamped."""
    with transaction.atomic():
        return publish_pending(AuthOutboxStore(), publisher, limit=limit)
