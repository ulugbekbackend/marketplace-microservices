"""Failure routing, dispatch and the consumer/relay loops, with the broker faked out."""

import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pika
import pytest
from pydantic import ValidationError

from contracts.enums import EventType
from contracts.events import EventEnvelope, OrderCreated, OrderItemRef, build_event
from py_common.context import get_correlation_id
from py_common.rabbit import (
    ERROR_HEADER,
    AioPikaConsumer,
    BlockingConsumer,
    PermanentError,
    envelope_properties,
    make_dispatch,
    redirect_failed,
    run_relay,
)
from py_common.retry import RETRY_COUNT_HEADER, RetryPolicy

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
POLICY = RetryPolicy((1_000, 5_000, 25_000))


def make_envelope() -> EventEnvelope:
    order_id = uuid4()
    payload = OrderCreated(order_id=order_id, items=[OrderItemRef(variant_id=uuid4(), qty=2)])
    return build_event(payload, producer="order", correlation_id=order_id, occurred_at=NOW)


# --- redirect_failed ----------------------------------------------------------------------


def test_first_failure_goes_to_retry_queue_with_first_delay() -> None:
    target = redirect_failed("catalog", None, RuntimeError("db down"), POLICY)
    assert target.queue == "catalog.q.retry"
    assert target.expiration_ms == 1_000
    assert target.headers[RETRY_COUNT_HEADER] == 1
    assert target.headers[ERROR_HEADER] == "RuntimeError: db down"


def test_delays_grow_with_each_attempt() -> None:
    delays = [
        redirect_failed("order", {RETRY_COUNT_HEADER: n}, RuntimeError(), POLICY).expiration_ms
        for n in range(3)
    ]
    assert delays == [1_000, 5_000, 25_000]


def test_exhausted_attempts_go_to_dlq() -> None:
    target = redirect_failed("order", {RETRY_COUNT_HEADER: 3}, RuntimeError(), POLICY)
    assert target.queue == "order.q.dlq"
    assert target.expiration_ms is None
    assert target.headers[RETRY_COUNT_HEADER] == 3


@pytest.mark.parametrize("error", [PermanentError("bad"), "validation"])
def test_permanent_errors_skip_retries(error: Any) -> None:
    if error == "validation":
        try:
            EventEnvelope.model_validate_json(b"{}")
        except ValidationError as exc:
            error = exc
    target = redirect_failed("search", None, error, POLICY)
    assert target.queue == "search.q.dlq"
    assert target.headers[RETRY_COUNT_HEADER] == 0


def test_broker_death_headers_are_dropped_and_others_kept() -> None:
    headers = {
        "x-death": [{"count": 1}],
        "x-first-death-queue": "catalog.q.retry",
        "x-last-death-reason": "expired",
        "trace": "abc",
        RETRY_COUNT_HEADER: 1,
    }
    target = redirect_failed("catalog", headers, RuntimeError(), POLICY)
    assert set(target.headers) == {"trace", RETRY_COUNT_HEADER, ERROR_HEADER}
    assert target.headers[RETRY_COUNT_HEADER] == 2


def test_long_error_messages_are_truncated() -> None:
    target = redirect_failed("catalog", None, RuntimeError("x" * 2_000), POLICY)
    assert len(target.headers[ERROR_HEADER]) == 500


# --- make_dispatch ------------------------------------------------------------------------


def test_dispatch_routes_by_event_type_inside_correlation_context() -> None:
    seen: list[tuple[UUID, UUID | None]] = []

    def handle(envelope: EventEnvelope) -> None:
        seen.append((envelope.event_id, get_correlation_id()))

    envelope = make_envelope()
    make_dispatch({EventType.ORDER_CREATED: handle})(envelope.model_dump_json().encode())
    assert seen == [(envelope.event_id, envelope.correlation_id)]


def test_dispatch_ignores_events_without_handler() -> None:
    make_dispatch({})(make_envelope().model_dump_json().encode())


def test_dispatch_rejects_malformed_body() -> None:
    with pytest.raises(ValidationError):
        make_dispatch({})(b'{"event_type": "nope"}')


# --- BlockingConsumer.process -------------------------------------------------------------


class FakeChannel:
    def __init__(self, fail_publish: bool = False) -> None:
        self.published: list[dict[str, Any]] = []
        self.acked: list[int] = []
        self._fail_publish = fail_publish

    def basic_publish(self, **kwargs: Any) -> None:
        if self._fail_publish:
            raise pika.exceptions.UnroutableError([])
        self.published.append(kwargs)

    def basic_ack(self, delivery_tag: int) -> None:
        self.acked.append(delivery_tag)


def consumer(handle: Any) -> BlockingConsumer:
    return BlockingConsumer("amqp://guest:guest@localhost/", "catalog", handle, policy=POLICY)


def test_success_is_acked_without_republish() -> None:
    channel = FakeChannel()
    envelope = make_envelope()
    bodies: list[bytes] = []
    consumer(bodies.append).process(
        channel,
        7,
        envelope_properties(envelope),
        envelope.model_dump_json().encode(),
    )
    assert channel.acked == [7]
    assert channel.published == []
    assert len(bodies) == 1


def test_failure_is_republished_to_retry_queue_then_acked() -> None:
    channel = FakeChannel()
    envelope = make_envelope()

    def boom(_body: bytes) -> None:
        raise RuntimeError("catalog db down")

    consumer(boom).process(
        channel,
        3,
        envelope_properties(envelope),
        b"payload",
    )
    assert channel.acked == [3]
    [published] = channel.published
    assert published["exchange"] == ""
    assert published["routing_key"] == "catalog.q.retry"
    assert published["body"] == b"payload"
    props = published["properties"]
    assert props.expiration == "1000"
    assert props.message_id == str(envelope.event_id)
    assert props.headers[RETRY_COUNT_HEADER] == 1
    assert props.delivery_mode == pika.DeliveryMode.Persistent.value


def test_delivery_stays_unacked_when_redirect_is_not_confirmed() -> None:
    channel = FakeChannel(fail_publish=True)

    def boom(_body: bytes) -> None:
        raise RuntimeError

    with pytest.raises(pika.exceptions.UnroutableError):
        consumer(boom).process(
            channel,
            1,
            pika.BasicProperties(headers={RETRY_COUNT_HEADER: 3}),
            b"x",
        )
    assert channel.acked == []


def test_envelope_properties() -> None:
    envelope = make_envelope()
    props = envelope_properties(envelope)
    assert props.type == "order.created"
    assert props.correlation_id == str(envelope.correlation_id)
    assert props.app_id == "order"
    assert props.content_type == "application/json"


# --- AioPikaConsumer.process --------------------------------------------------------------


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[Any, str]] = []

    async def publish(self, message: Any, routing_key: str) -> None:
        self.published.append((message, routing_key))


class FakeMessage:
    def __init__(self, headers: dict[str, Any] | None = None) -> None:
        self.body = b"body"
        self.headers = headers or {}
        self.content_type = "application/json"
        self.message_id = "m-1"
        self.correlation_id = "c-1"
        self.type = "order.created"
        self.timestamp = NOW
        self.app_id = "order"
        self.acked = False

    async def ack(self) -> None:
        self.acked = True


def aio_consumer(handle: Any) -> tuple[AioPikaConsumer, FakeExchange]:
    exchange = FakeExchange()
    instance = AioPikaConsumer("amqp://localhost/", "search", handle, policy=POLICY)
    instance._channel = SimpleNamespace(default_exchange=exchange)  # type: ignore[assignment]
    return instance, exchange


async def test_async_success_is_acked() -> None:
    seen: list[bytes] = []

    async def handle(body: bytes) -> None:
        seen.append(body)

    instance, exchange = aio_consumer(handle)
    message = FakeMessage()
    await instance.process(message)  # type: ignore[arg-type]
    assert message.acked and seen == [b"body"] and exchange.published == []


async def test_async_last_failure_goes_to_dlq() -> None:
    async def handle(_body: bytes) -> None:
        raise RuntimeError("es down")

    instance, exchange = aio_consumer(handle)
    message = FakeMessage({RETRY_COUNT_HEADER: 3})
    await instance.process(message)  # type: ignore[arg-type]
    assert message.acked
    [(republished, routing_key)] = exchange.published
    assert routing_key == "search.q.dlq"
    assert republished.expiration is None
    assert republished.headers[ERROR_HEADER] == "RuntimeError: es down"


async def test_async_failure_is_delayed_in_retry_queue() -> None:
    async def handle(_body: bytes) -> None:
        raise RuntimeError

    instance, exchange = aio_consumer(handle)
    await instance.process(FakeMessage())  # type: ignore[arg-type]
    [(republished, routing_key)] = exchange.published
    assert routing_key == "search.q.retry"
    assert republished.headers[RETRY_COUNT_HEADER] == 1
    assert republished.expiration is not None


# --- run_relay ----------------------------------------------------------------------------


def test_relay_keeps_draining_while_batches_are_full_and_survives_errors() -> None:
    stop = threading.Event()
    results: list[int | Exception] = [100, 100, RuntimeError("broker down"), 0]
    calls = 0

    def batch() -> int:
        nonlocal calls
        calls += 1
        result = results.pop(0)
        if not results:
            stop.set()
        if isinstance(result, Exception):
            raise result
        return result

    run_relay(batch, stop, interval=0)
    assert calls == 4


def test_relay_does_nothing_once_stopped() -> None:
    stop = threading.Event()
    stop.set()
    run_relay(lambda: pytest.fail("must not run"), stop)
