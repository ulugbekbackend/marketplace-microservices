"""The outbox table: rows only inside a transaction, published once, consumers deduplicated."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.db import transaction

from contracts.events import EventEnvelope, OrderExpired, OrderItemRef, build_event
from messaging.models import Outbox
from messaging.outbox import (
    DjangoOutboxStore,
    OutsideTransactionError,
    add_to_outbox,
    mark_processed,
)
from py_common.outbox import publish_pending

pytestmark = pytest.mark.django_db


def _event() -> EventEnvelope:
    return build_event(
        OrderExpired(order_id=uuid4(), items=[OrderItemRef(variant_id=uuid4(), qty=1)]),
        producer="order",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.django_db(transaction=True)
def test_outbox_requires_a_transaction() -> None:
    with pytest.raises(OutsideTransactionError):
        add_to_outbox(_event())
    with pytest.raises(OutsideTransactionError):
        mark_processed(_event())


def test_store_publishes_pending_rows_once() -> None:
    with transaction.atomic():
        first = add_to_outbox(_event())
        second = add_to_outbox(_event())

    class Recorder:
        def __init__(self) -> None:
            self.sent: list[EventEnvelope] = []

        def publish(self, envelope: EventEnvelope) -> None:
            self.sent.append(envelope)

    publisher = Recorder()
    store = DjangoOutboxStore()
    with transaction.atomic():
        assert publish_pending(store, publisher) == 2
    with transaction.atomic():
        assert publish_pending(store, publisher) == 0

    assert [e.event_id for e in publisher.sent] == [first.event_id, second.event_id]
    assert publisher.sent[0].producer == "order"
    assert not Outbox.objects.filter(published_at__isnull=True).exists()


def test_processed_events_are_recorded_once() -> None:
    event = _event()

    with transaction.atomic():
        assert mark_processed(event) is True
    with transaction.atomic():
        assert mark_processed(event) is False
