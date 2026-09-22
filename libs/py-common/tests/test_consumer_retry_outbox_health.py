"""Consumer routing and idempotency, retry policy, outbox publishing, readiness checks."""

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from contracts.enums import EventType
from contracts.events import EventEnvelope, OrderCreated, OrderItemRef, ProductDeleted, build_event
from py_common.consumer import EventRouter, Outcome
from py_common.health import HealthRegistry
from py_common.idempotency import MemoryIdempotencyStore
from py_common.outbox import PendingEvent, publish_pending
from py_common.retry import DeadLetter, Retry, RetryPolicy, attempt_from_headers

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def make_envelope(order_id: UUID | None = None) -> EventEnvelope:
    order_id = order_id or uuid4()
    payload = OrderCreated(order_id=order_id, items=[OrderItemRef(variant_id=uuid4(), qty=1)])
    return build_event(payload, producer="order", correlation_id=order_id, occurred_at=NOW)


async def test_router_handles_registered_event() -> None:
    router = EventRouter("catalog", MemoryIdempotencyStore())
    seen: list[UUID] = []

    @router.on(EventType.ORDER_CREATED)
    async def handle(envelope: EventEnvelope) -> None:
        seen.append(envelope.event_id)

    envelope = make_envelope()
    assert await router.dispatch(envelope.model_dump_json()) is Outcome.HANDLED
    assert seen == [envelope.event_id]
    assert router.handled_types == frozenset({EventType.ORDER_CREATED})


async def test_duplicate_event_is_handled_once() -> None:
    router = EventRouter("catalog", MemoryIdempotencyStore())
    calls = 0

    @router.on(EventType.ORDER_CREATED)
    async def handle(envelope: EventEnvelope) -> None:
        nonlocal calls
        calls += 1

    raw = make_envelope().model_dump_json()
    assert await router.dispatch(raw) is Outcome.HANDLED
    assert await router.dispatch(raw) is Outcome.DUPLICATE
    assert calls == 1


async def test_unregistered_event_is_ignored_without_marking_it_processed() -> None:
    store = MemoryIdempotencyStore()
    router = EventRouter("catalog", store)
    envelope = build_event(
        ProductDeleted(product_id=uuid4()),
        producer="catalog",
        correlation_id=uuid4(),
        occurred_at=NOW,
    )

    assert await router.dispatch(envelope.model_dump_json()) is Outcome.IGNORED
    assert await store.mark_processed(envelope.event_id) is True


async def test_handler_error_propagates_to_the_broker_wiring() -> None:
    router = EventRouter("catalog", MemoryIdempotencyStore())

    @router.on(EventType.ORDER_CREATED)
    async def handle(envelope: EventEnvelope) -> None:
        raise RuntimeError("database down")

    with pytest.raises(RuntimeError, match="database down"):
        await router.dispatch(make_envelope().model_dump_json())


async def test_duplicate_handler_registration_is_rejected() -> None:
    router = EventRouter("catalog", MemoryIdempotencyStore())

    @router.on(EventType.ORDER_CREATED)
    async def first(envelope: EventEnvelope) -> None: ...

    with pytest.raises(ValueError, match="already registered"):
        router.on(EventType.ORDER_CREATED)(first)


def test_retry_policy_grows_then_dead_letters() -> None:
    policy = RetryPolicy((1_000, 5_000, 25_000))
    assert policy.decide(0) == Retry(delay_ms=1_000, attempt=1)
    assert policy.decide(1) == Retry(delay_ms=5_000, attempt=2)
    assert policy.decide(2) == Retry(delay_ms=25_000, attempt=3)
    assert policy.decide(3) == DeadLetter(attempts=3)
    assert policy.max_attempts == 3


def test_retry_policy_validates_input() -> None:
    with pytest.raises(ValueError, match="delay"):
        RetryPolicy(())
    with pytest.raises(ValueError, match="attempt"):
        RetryPolicy().decide(-1)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [(None, 0), ({}, 0), ({"x-retry-count": 2}, 2), ({"x-retry-count": "3"}, 3)],
)
def test_attempt_from_headers(headers: dict[str, object] | None, expected: int) -> None:
    assert attempt_from_headers(headers) == expected


@pytest.mark.parametrize("value", ["oops", None, -5])
def test_attempt_from_broken_header_falls_back_to_zero(value: object) -> None:
    assert attempt_from_headers({"x-retry-count": value}) == 0


class FakeStore:
    def __init__(self, rows: list[PendingEvent]) -> None:
        self.rows = rows
        self.published: list[int | UUID] = []

    def fetch_unpublished(self, limit: int) -> list[PendingEvent]:
        return self.rows[:limit]

    def mark_published(self, ids: Iterable[int | UUID]) -> None:
        self.published.extend(ids)


class FakePublisher:
    def __init__(self, fail_from: int | None = None) -> None:
        self.sent: list[EventEnvelope] = []
        self.fail_from = fail_from

    def publish(self, envelope: EventEnvelope) -> None:
        if self.fail_from is not None and len(self.sent) >= self.fail_from:
            raise ConnectionError("broker unavailable")
        self.sent.append(envelope)


def test_outbox_publishes_batch_and_marks_rows() -> None:
    rows = [PendingEvent(id=index, envelope=make_envelope()) for index in range(3)]
    store, publisher = FakeStore(rows), FakePublisher()

    assert publish_pending(store, publisher) == 3
    assert store.published == [0, 1, 2]
    assert len(publisher.sent) == 3


def test_outbox_stops_at_first_failure_and_keeps_rest_unpublished() -> None:
    rows = [PendingEvent(id=index, envelope=make_envelope()) for index in range(3)]
    store, publisher = FakeStore(rows), FakePublisher(fail_from=1)

    assert publish_pending(store, publisher) == 1
    assert store.published == [0]


def test_outbox_marks_nothing_when_the_broker_is_down() -> None:
    rows = [PendingEvent(id=1, envelope=make_envelope())]
    store, publisher = FakeStore(rows), FakePublisher(fail_from=0)

    assert publish_pending(store, publisher) == 0
    assert store.published == []


async def test_health_reports_every_check() -> None:
    registry = HealthRegistry()

    async def ok() -> None:
        return None

    async def broken() -> None:
        raise ConnectionError("redis refused")

    registry.add("postgres", ok)
    registry.add("redis", broken)

    report = await registry.run()
    assert report.ok is False
    body = report.as_dict()
    assert body["status"] == "unavailable"
    assert body["checks"]["postgres"] == {"ok": True}
    assert "redis refused" in body["checks"]["redis"]["error"]


async def test_health_times_out_a_hanging_check() -> None:
    registry = HealthRegistry(timeout=0.05)

    async def hangs() -> None:
        await asyncio.sleep(5)

    registry.add("elasticsearch", hangs)
    report = await registry.run()
    assert report.ok is False
    assert report.checks[0].error == "timeout"


async def test_health_is_ok_when_all_checks_pass() -> None:
    registry = HealthRegistry()

    async def ok() -> None:
        return None

    registry.add("postgres", ok)
    report = await registry.run()
    assert report.ok is True
    assert report.as_dict()["status"] == "ok"
