"""Outbox relay: seller.approved rows reach the broker unchanged, once, in write order."""

import threading
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import connection, transaction

from accounts import sellers
from accounts.management.commands import relay_outbox
from accounts.models import Outbox, Role
from accounts.outbox import AuthOutboxStore, relay_batch
from contracts.events import EventEnvelope, SellerApproved, build_event
from tests.factories import make_application, make_user


def _write(shop_name: str = "x") -> Outbox:
    envelope = build_event(
        SellerApproved(user_id=uuid4(), shop_name=shop_name),
        producer="auth",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )
    with transaction.atomic():
        return sellers.write_event(envelope)


class Recorder:
    def __init__(self, *, fail_on: int | None = None) -> None:
        self.sent: list[EventEnvelope] = []
        self.closed = False
        self._fail_on = fail_on

    def publish(self, envelope: EventEnvelope) -> None:
        if self._fail_on is not None and len(self.sent) == self._fail_on:
            raise ConnectionError("broker down")
        self.sent.append(envelope)

    def idle(self, seconds: float) -> None:
        time.sleep(seconds)

    def close(self) -> None:
        self.closed = True


@pytest.mark.django_db
def test_approval_event_is_published_as_written() -> None:
    admin = make_user(role=Role.ADMIN)
    application = make_application()
    sellers.approve(application.id, reviewer_id=admin.id)
    row = Outbox.objects.get()
    publisher = Recorder()

    assert relay_batch(publisher) == 1

    [sent] = publisher.sent
    assert sent == EventEnvelope.model_validate(row.payload)
    assert sent.producer == "auth"
    row.refresh_from_db()
    assert row.published_at is not None
    assert relay_batch(publisher) == 0


@pytest.mark.django_db
def test_rows_go_out_in_write_order_and_a_failure_stops_the_batch() -> None:
    rows = [_write(f"shop {n}") for n in range(3)]
    publisher = Recorder(fail_on=2)

    assert relay_batch(publisher) == 2

    assert [e.event_id for e in publisher.sent] == [rows[0].event_id, rows[1].event_id]
    [pending] = Outbox.objects.filter(published_at__isnull=True)
    assert pending.event_id == rows[2].event_id


@pytest.mark.django_db
def test_batch_size_is_respected() -> None:
    for _ in range(3):
        _write()

    assert relay_batch(Recorder(), limit=2) == 2
    assert relay_batch(Recorder(), limit=2) == 1


@pytest.mark.django_db(transaction=True)
def test_rows_locked_by_another_relay_are_skipped() -> None:
    first, second = _write(), _write()
    locked = threading.Event()
    done = threading.Event()

    def hold_first() -> None:
        try:
            with transaction.atomic():
                list(Outbox.objects.select_for_update().filter(id=first.id))
                locked.set()
                done.wait(10)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_first)
    holder.start()
    try:
        assert locked.wait(10)
        with transaction.atomic():
            pending = AuthOutboxStore().fetch_unpublished(10)
    finally:
        done.set()
        holder.join()

    assert [row.id for row in pending] == [second.id]


@pytest.mark.django_db(transaction=True)
def test_command_publishes_until_stopped_and_closes_the_publisher(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.RABBITMQ_URL = "amqp://relay-test:5672/"
    row = _write()
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

    call_command("relay_outbox", "--interval", "0.01", "--batch-size", "5")

    assert urls == ["amqp://relay-test:5672/"]
    assert [e.event_id for e in publisher.sent] == [row.event_id]
    assert publisher.closed
    assert not Outbox.objects.filter(published_at__isnull=True).exists()


@pytest.mark.django_db(transaction=True)
def test_command_closes_the_publisher_when_the_loop_dies(
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
