"""Money arithmetic, UUIDv7 ordering and the RabbitMQ topology document."""

from decimal import Decimal

import pytest

from contracts.enums import EventType
from contracts.ids import uuid7
from contracts.money import apply_commission, format_tiyin, som_to_tiyin
from contracts.topology import (
    CONSUMER_BINDINGS,
    EXCHANGE,
    RETRY_EXCHANGE,
    dlq_name,
    queue_name,
    render_definitions,
    retry_queue_name,
)


@pytest.mark.parametrize(
    ("som", "expected"),
    [(0, 0), (1, 100), (1_250_000, 125_000_000), ("12.345", 1_235), (Decimal("0.005"), 1)],
)
def test_som_to_tiyin(som: int | str | Decimal, expected: int) -> None:
    assert som_to_tiyin(som) == expected


@pytest.mark.parametrize(
    ("gross", "rate", "expected"),
    [
        (125_000_000, Decimal("0.10"), 12_500_000),
        (333, Decimal("0.15"), 50),  # 49.95 rounds half up
        (0, Decimal("0.10"), 0),
        (100, Decimal("0"), 0),
        (100, Decimal("1"), 100),
    ],
)
def test_apply_commission(gross: int, rate: Decimal, expected: int) -> None:
    assert apply_commission(gross, rate) == expected


def test_commission_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="gross_tiyin"):
        apply_commission(-1, Decimal("0.1"))
    with pytest.raises(ValueError, match="rate"):
        apply_commission(100, Decimal("1.5"))


def test_seller_net_plus_commission_equals_gross() -> None:
    gross = 1_234_567
    commission = apply_commission(gross, Decimal("0.1234"))
    assert commission + (gross - commission) == gross


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(125_000_000, "1\u00a0250\u00a0000 so'm"), (0, "0 so'm"), (150, "1,50 so'm")],
)
def test_format_tiyin(amount: int, expected: str) -> None:
    assert format_tiyin(amount) == expected


def test_uuid7_is_version_7_and_time_ordered() -> None:
    values = [uuid7() for _ in range(50)]
    assert all(value.version == 7 for value in values)
    assert len(set(values)) == len(values)
    assert [str(v) for v in values] == sorted(str(v) for v in values)


def test_definitions_cover_every_consumer() -> None:
    definitions = render_definitions()
    queues = {queue["name"] for queue in definitions["queues"]}
    for service in CONSUMER_BINDINGS:
        assert {queue_name(service), retry_queue_name(service), dlq_name(service)} <= queues


def test_definitions_bind_every_consumed_event() -> None:
    definitions = render_definitions()
    bound = {
        (binding["destination"], binding["routing_key"])
        for binding in definitions["bindings"]
        if binding["source"] == EXCHANGE
    }
    for service, events in CONSUMER_BINDINGS.items():
        for event in events:
            assert (queue_name(service), str(event)) in bound


def test_definitions_have_no_credentials() -> None:
    definitions = render_definitions()
    assert "users" not in definitions
    assert definitions["permissions"] == []


def test_retry_queue_dead_letters_back_to_main_queue() -> None:
    definitions = render_definitions()
    retry = next(q for q in definitions["queues"] if q["name"] == retry_queue_name("order"))
    assert retry["arguments"]["x-dead-letter-exchange"] == RETRY_EXCHANGE
    assert retry["arguments"]["x-dead-letter-routing-key"] == queue_name("order")


def test_every_event_is_consumed_by_someone() -> None:
    consumed = {event for events in CONSUMER_BINDINGS.values() for event in events}
    assert consumed == set(EventType)


def test_uuid7_is_monotonic_under_threads() -> None:
    import threading

    produced: list[list[str]] = []
    lock = threading.Lock()

    def worker() -> None:
        values = [str(uuid7()) for _ in range(200)]
        with lock:
            produced.append(values)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    flat = [value for chunk in produced for value in chunk]
    assert len(set(flat)) == len(flat)
    for chunk in produced:
        assert chunk == sorted(chunk)
