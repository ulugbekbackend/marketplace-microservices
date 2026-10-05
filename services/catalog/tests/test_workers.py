"""Long running workers: outbox relay, event consumer, and the stale reservation sweep."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone

from config.celery import app as celery_app
from contracts.enums import EventType
from contracts.events import (
    EventEnvelope,
    OrderCreated,
    OrderItemRef,
    ProductUpdated,
    SellerApproved,
    build_event,
)
from messaging.management.commands import consume_events, relay_outbox
from messaging.models import Outbox
from messaging.outbox import add_to_outbox, relay_batch
from products import stock
from products.models import StockReservation
from products.tasks import release_stale_reservations
from tests.factories import make_reservation, make_variant

GRACE = timedelta(minutes=10)


def _event() -> EventEnvelope:
    return build_event(
        SellerApproved(user_id=uuid4(), shop_name="x"),
        producer="catalog",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )


class Recorder:
    def __init__(self, *, fail_on: int | None = None) -> None:
        self.sent: list[EventEnvelope] = []
        self.closed = False
        self._fail_on = fail_on

    def publish(self, envelope: EventEnvelope) -> None:
        if self._fail_on is not None and len(self.sent) == self._fail_on:
            raise ConnectionError("broker down")
        self.sent.append(envelope)

    def close(self) -> None:
        self.closed = True


# --- relay --------------------------------------------------------------------------------


@pytest.mark.django_db
def test_relay_batch_publishes_in_order_and_stops_at_a_failure() -> None:
    with transaction.atomic():
        rows = [add_to_outbox(_event()) for _ in range(3)]
    publisher = Recorder(fail_on=1)

    assert relay_batch(publisher) == 1

    assert [e.event_id for e in publisher.sent] == [rows[0].event_id]
    pending = Outbox.objects.filter(published_at__isnull=True).order_by("id")
    assert [row.event_id for row in pending] == [rows[1].event_id, rows[2].event_id]


@pytest.mark.django_db
def test_relay_batch_respects_the_limit() -> None:
    with transaction.atomic():
        for _ in range(3):
            add_to_outbox(_event())
    publisher = Recorder()

    assert relay_batch(publisher, limit=2) == 2
    assert relay_batch(publisher, limit=2) == 1
    assert relay_batch(publisher, limit=2) == 0


@pytest.mark.django_db(transaction=True)
def test_relay_command_publishes_until_stopped_and_closes_the_publisher(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.RABBITMQ_URL = "amqp://relay-test:5672/"
    with transaction.atomic():
        row = add_to_outbox(_event())
    stop = threading.Event()
    publisher = Recorder()
    urls: list[str] = []

    def fake_publisher(url: str) -> Recorder:
        urls.append(url)
        return publisher

    original_publish = publisher.publish

    def publish_then_stop(envelope: EventEnvelope) -> None:
        original_publish(envelope)
        stop.set()

    monkeypatch.setattr(publisher, "publish", publish_then_stop)
    monkeypatch.setattr(relay_outbox, "PikaPublisher", fake_publisher)
    monkeypatch.setattr(relay_outbox, "stop_on_signals", lambda: stop)

    call_command("relay_outbox", "--interval", "0.01")

    assert urls == ["amqp://relay-test:5672/"]
    assert [e.event_id for e in publisher.sent] == [row.event_id]
    assert publisher.closed
    assert not Outbox.objects.filter(published_at__isnull=True).exists()


@pytest.mark.django_db(transaction=True)
def test_relay_command_closes_the_publisher_when_the_loop_dies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = Recorder()

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("loop died")

    monkeypatch.setattr(relay_outbox, "PikaPublisher", lambda url: publisher)
    monkeypatch.setattr(relay_outbox, "stop_on_signals", threading.Event)
    monkeypatch.setattr(relay_outbox, "run_relay", boom)

    with pytest.raises(RuntimeError, match="loop died"):
        call_command("relay_outbox")
    assert publisher.closed


# --- consumer -----------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_consume_command_wires_the_catalog_queue_to_the_handlers(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.RABBITMQ_URL = "amqp://consume-test:5672/"
    started: dict[str, Any] = {}
    stop = threading.Event()

    class FakeConsumer:
        def __init__(self, url: str, service: str, handle: Callable[[bytes], object]) -> None:
            started.update(url=url, service=service, handle=handle)

        def run(self, stop_event: threading.Event) -> None:
            started["stop"] = stop_event

    monkeypatch.setattr(consume_events, "BlockingConsumer", FakeConsumer)
    monkeypatch.setattr(consume_events, "stop_on_signals", lambda: stop)

    call_command("consume_events")

    assert started["url"] == "amqp://consume-test:5672/"
    assert started["service"] == "catalog"
    assert started["stop"] is stop

    variant = make_variant(stock=3)
    envelope = build_event(
        OrderCreated(order_id=uuid4(), items=[OrderItemRef(variant_id=variant.id, qty=1)]),
        producer="order",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )
    started["handle"](envelope.model_dump_json().encode())

    variant.refresh_from_db()
    assert variant.reserved == 1
    assert Outbox.objects.filter(event_type=EventType.STOCK_RESERVED.value).count() == 1


# --- stale reservation sweep ----------------------------------------------------------------


def _expired(minutes_ago: int, **fields: Any) -> StockReservation:
    variant = fields.pop("variant", None) or make_variant(stock=5, reserved=0)
    qty = fields.pop("qty", 1)
    variant.reserved += qty
    variant.save(update_fields=["reserved"])
    return make_reservation(
        variant=variant,
        qty=qty,
        expires_at=timezone.now() - timedelta(minutes=minutes_ago),
        **fields,
    )


@pytest.mark.django_db
def test_sweep_releases_only_reservations_long_past_expiry() -> None:
    stale = _expired(11)
    recent = _expired(5)
    committed = _expired(30, status="committed")

    assert release_stale_reservations() == 1

    stale.refresh_from_db()
    recent.refresh_from_db()
    committed.refresh_from_db()
    assert (stale.status, recent.status, committed.status) == ("released", "active", "committed")
    stale.variant.refresh_from_db()
    assert stale.variant.reserved == 0
    assert release_stale_reservations() == 0


@pytest.mark.django_db
def test_sweep_releases_a_whole_order_and_reindexes_a_sold_out_product() -> None:
    order_id = uuid4()
    sold_out = make_variant(stock=1)
    other = make_variant(stock=5)
    _expired(20, variant=sold_out, order_id=order_id)
    _expired(20, variant=other, order_id=order_id, qty=2)

    assert release_stale_reservations() == 1

    assert set(StockReservation.objects.values_list("status", flat=True)) == {"released"}
    [update] = Outbox.objects.filter(event_type=EventType.PRODUCT_UPDATED.value)
    document = ProductUpdated.model_validate(update.payload)
    assert (document.product_id, document.in_stock) == (sold_out.product_id, True)


@pytest.mark.django_db
def test_sweep_works_in_batches() -> None:
    for _ in range(3):
        _expired(15)

    assert stock.release_stale(grace=GRACE, limit=2) == 2
    assert stock.release_stale(grace=GRACE, limit=2) == 1


@pytest.mark.django_db(transaction=True)
def test_sweep_skips_an_order_another_worker_holds() -> None:
    held = _expired(15)
    locked = threading.Event()
    done = threading.Event()

    def hold_the_rows() -> None:
        try:
            with transaction.atomic():
                list(StockReservation.objects.select_for_update().filter(id=held.id))
                locked.set()
                done.wait(10)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_rows)
    holder.start()
    try:
        assert locked.wait(10)
        assert stock.release_stale(grace=GRACE) == 0  # no waiting on the other worker
    finally:
        done.set()
        holder.join()

    assert stock.release_stale(grace=GRACE) == 1


@pytest.mark.django_db
def test_sweep_leaves_an_order_that_was_reserved_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """A late payment re-reserved the order between the scan and the lock."""
    reservation = _expired(15)
    original = stock._order_products

    def reserve_again_first(order_id: Any) -> set[Any]:
        StockReservation.objects.filter(id=reservation.id).update(
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        return original(order_id)

    monkeypatch.setattr(stock, "_order_products", reserve_again_first)

    assert stock.release_stale(grace=GRACE) == 0

    reservation.refresh_from_db()
    assert reservation.status == "active"


def test_sweep_runs_every_minute_on_beat() -> None:
    entry = celery_app.conf.beat_schedule["release-stale-reservations"]

    assert entry["schedule"] == 60.0
    assert entry["task"] == release_stale_reservations.name
