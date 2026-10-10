"""The long-running commands: outbox relay and event consumer, with fakes for RabbitMQ."""

import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from contracts.enums import OrderStatus
from contracts.events import EventEnvelope, OrderExpired, OrderItemRef, StockReserved
from messaging.management.commands import relay_outbox
from messaging.models import Outbox
from orders import services
from orders.management.commands import consume_events
from orders.models import Order
from tests.conftest import incoming
from tests.factories import make_order

pytestmark = pytest.mark.django_db

RABBIT = "amqp://relay.test:5672/"


class FakePublisher:
    """Records what the relay sends; fails the first ``fail_first`` publishes."""

    def __init__(self, stop: threading.Event, *, expected: int, fail_first: int = 0) -> None:
        self.stop = stop
        self.expected = expected
        self.fail_first = fail_first
        self.url = ""
        self.sent: list[EventEnvelope] = []
        self.closed = False

    def __call__(self, url: str) -> "FakePublisher":  # stands in for the PikaPublisher class
        self.url = url
        return self

    def publish(self, envelope: EventEnvelope) -> None:
        if self.fail_first:
            self.fail_first -= 1
            raise ConnectionError("broker down")
        self.sent.append(envelope)
        if len(self.sent) >= self.expected:
            self.stop.set()

    def idle(self, seconds: float) -> None:
        self.stop.wait(seconds)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def stop(monkeypatch: pytest.MonkeyPatch, settings: Any) -> threading.Event:
    settings.RABBITMQ_URL = RABBIT
    event = threading.Event()
    monkeypatch.setattr(relay_outbox, "stop_on_signals", lambda: event)
    monkeypatch.setattr(consume_events, "stop_on_signals", lambda: event)
    return event


def pending_events(count: int) -> list[Outbox]:
    with transaction.atomic():
        order = make_order()
        for _ in range(count):
            services.publish(
                order,
                OrderExpired(order_id=order.id, items=[OrderItemRef(variant_id=uuid4(), qty=1)]),
            )
    return list(Outbox.objects.order_by("id"))


def test_relay_publishes_every_row_in_batches_then_closes(
    monkeypatch: pytest.MonkeyPatch, stop: threading.Event, recycled_connections: list[str]
) -> None:
    rows = pending_events(5)
    publisher = FakePublisher(stop, expected=5)
    monkeypatch.setattr(relay_outbox, "PikaPublisher", publisher)

    call_command("relay_outbox", "--batch-size", "2", "--interval", "0.01")

    assert publisher.url == RABBIT
    assert [e.event_id for e in publisher.sent] == [row.event_id for row in rows]
    assert {e.producer for e in publisher.sent} == {"order"}
    assert not Outbox.objects.filter(published_at__isnull=True).exists()
    assert publisher.closed
    assert recycled_connections.count(relay_outbox.__name__) == 3  # 2 + 2 + 1


def test_relay_retries_a_row_the_broker_did_not_confirm(
    monkeypatch: pytest.MonkeyPatch, stop: threading.Event
) -> None:
    [row] = pending_events(1)
    publisher = FakePublisher(stop, expected=1, fail_first=1)
    monkeypatch.setattr(relay_outbox, "PikaPublisher", publisher)

    call_command("relay_outbox", "--interval", "0.01")

    assert [e.event_id for e in publisher.sent] == [row.event_id]
    assert Outbox.objects.get().published_at is not None


def test_relay_closes_the_publisher_when_stopped_at_once(
    monkeypatch: pytest.MonkeyPatch, stop: threading.Event
) -> None:
    pending_events(1)
    publisher = FakePublisher(stop, expected=1)
    monkeypatch.setattr(relay_outbox, "PikaPublisher", publisher)
    stop.set()

    call_command("relay_outbox")

    assert publisher.sent == []
    assert publisher.closed
    assert Outbox.objects.get().published_at is None


def test_consumer_reads_the_order_queue_and_feeds_the_saga(
    monkeypatch: pytest.MonkeyPatch, stop: threading.Event, recycled_connections: list[str]
) -> None:
    order = make_order(status=OrderStatus.PENDING)
    started: dict[str, Any] = {}

    class FakeConsumer:
        def __init__(self, url: str, service: str, handle: Callable[[bytes], None]) -> None:
            started.update(url=url, service=service)
            self.handle = handle

        def run(self, stop_event: threading.Event) -> None:
            started["stop"] = stop_event
            event = incoming(
                StockReserved(order_id=order.id, expires_at=timezone.now() + timedelta(minutes=5))
            )
            self.handle(event.model_dump_json().encode())

    monkeypatch.setattr(consume_events, "BlockingConsumer", FakeConsumer)
    metrics_ports: list[int] = []
    monkeypatch.setattr(consume_events, "serve", metrics_ports.append)

    call_command("consume_events")

    assert started == {"url": RABBIT, "service": "order", "stop": stop}
    assert metrics_ports == [9100]
    assert Order.objects.get(id=order.id).status == OrderStatus.RESERVED.value
    assert recycled_connections == [consume_events.__name__]
