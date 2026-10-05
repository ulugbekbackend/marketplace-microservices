"""Order saga against the running stack: the six scenarios of the checkout flow.

Run with `make test-integration` after `make up`. Needs DEBUG=True (dev OTP master code),
the broker published on the host (HOST_RABBITMQ_PORT) and the docker CLI, which ends a
reservation early through `manage.py expire_orders --order`.

The payment service arrives in a later phase, so the tests publish `payment.paid` on the
exchange themselves, exactly as that service will.
"""

import json
import os
import random
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pika
import pytest
from decouple import Config, RepositoryEnv

from contracts.enums import EventType, PaymentProvider
from contracts.events import EventEnvelope, PaymentPaid, build_event
from contracts.topology import EXCHANGE
from py_common.rabbit import envelope_properties

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1")
API_HOST = {"Host": "api.localhost"}
MASTER_CODE = "000000"
SETTLE_SECONDS = 20
ADDRESS = {
    "full_name": "Saga Test",
    "phone": "+998901234567",
    "region": "Toshkent",
    "city": "Toshkent",
    "street": "Amir Temur 1",
}

env = Config(RepositoryEnv(str(ROOT / ".env")))


def broker_url() -> str:
    """The compose RABBITMQ_URL, pointed at the port the broker publishes on the host."""
    url: str = env("RABBITMQ_URL")
    host_port = env("HOST_RABBITMQ_PORT", default="5672")
    return url.replace("@rabbitmq:5672", f"@127.0.0.1:{host_port}")


# --- event tap ----------------------------------------------------------------------------


class EventTap:
    """A private queue bound to the exchange: records every event the services publish."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._events: list[EventEnvelope] = []
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> "EventTap":
        self._thread.start()
        assert self._ready.wait(10), "event tap could not bind to the broker"
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(5)

    def _run(self) -> None:
        connection = pika.BlockingConnection(pika.URLParameters(self._url))
        channel = connection.channel()
        queue = channel.queue_declare("", exclusive=True).method.queue
        channel.queue_bind(queue, EXCHANGE, "#")
        self._ready.set()
        for method, _props, body in channel.consume(queue, auto_ack=True, inactivity_timeout=0.2):
            if self._stop.is_set():
                break
            if method is not None:
                with self._lock:
                    self._events.append(EventEnvelope.model_validate_json(body))
        connection.close()

    def of(self, event_type: EventType, order_id: str) -> list[EventEnvelope]:
        with self._lock:
            return [
                e
                for e in self._events
                if e.event_type is event_type and str(e.payload.get("order_id")) == order_id
            ]

    def wait_for(self, event_type: EventType, order_id: str) -> EventEnvelope:
        events = wait_until(lambda: self.of(event_type, order_id), f"{event_type} for {order_id}")
        return events[0]


def wait_until(probe: Callable[[], Any], what: str, timeout: float = SETTLE_SECONDS) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what}")


# --- stack helpers ------------------------------------------------------------------------


class Shopper:
    """A logged in customer with its own HTTP session."""

    def __init__(self) -> None:
        self.http = httpx.Client(base_url=GATEWAY, headers=API_HOST, timeout=10)
        phone = f"+99890{random.randint(1_000_000, 9_999_999)}"
        assert self._otp("send/", {"phone": phone}).status_code == 204
        verified = self._otp("verify/", {"phone": phone, "code": MASTER_CODE})
        assert verified.status_code == 200, verified.text
        self.http.headers["Authorization"] = f"Bearer {verified.json()['access']}"

    def _otp(self, path: str, body: dict[str, str]) -> httpx.Response:
        """The gateway allows 5 OTP calls a minute per address: wait out a 429."""
        for _ in range(8):
            response = self.http.post(f"/api/auth/otp/{path}", json=body)
            if response.status_code != 429:
                return response
            time.sleep(float(response.headers.get("Retry-After", "13")) + 0.5)
        return response

    def checkout(self, variant_id: str, qty: int) -> str:
        self.http.delete("/api/cart/")
        added = self.http.post("/api/cart/items/", json={"variant_id": variant_id, "qty": qty})
        assert added.status_code == 200, added.text
        response = self.http.post(
            "/api/orders/checkout/",
            json={"address": ADDRESS},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "PENDING"
        return str(response.json()["order_id"])

    def order(self, order_id: str) -> dict[str, Any]:
        response = self.http.get(f"/api/orders/{order_id}/")
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def wait_status(self, order_id: str, *statuses: str) -> dict[str, Any]:
        def settled() -> dict[str, Any] | None:
            order = self.order(order_id)
            return order if order["status"] in statuses else None

        result: dict[str, Any] = wait_until(settled, f"order {order_id} in {statuses}")
        return result

    def cancel(self, order_id: str) -> None:
        response = self.http.post(f"/api/orders/{order_id}/cancel/")
        assert response.status_code == 200, response.text


def available(http: httpx.Client, slug: str, variant_id: str) -> int:
    detail = http.get(f"/api/catalog/products/{slug}/").json()
    [variant] = [v for v in detail["variants"] if v["id"] == variant_id]
    return int(variant["available"])


def wait_available(http: httpx.Client, slug: str, variant_id: str, expected: int) -> None:
    wait_until(
        lambda: available(http, slug, variant_id) == expected,
        f"variant {variant_id} to have {expected} available",
    )


def expire_now(order_id: str) -> None:
    """End the reservation through the order service instead of waiting 15 minutes."""
    subprocess.run(
        [
            "docker", "compose", "-f", "infra/docker-compose.yml", "--env-file", ".env",
            "exec", "-T", "order", "python", "manage.py", "expire_orders", "--order", order_id,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )  # fmt: skip


def publish_payment(
    order_id: str, amount_tiyin: int, *, event_id: uuid.UUID | None = None
) -> uuid.UUID:
    """What the payment service publishes once a provider confirms the money."""
    envelope = build_event(
        PaymentPaid(
            order_id=uuid.UUID(order_id),
            transaction_id=uuid.uuid4(),
            amount_tiyin=amount_tiyin,
            provider=PaymentProvider.MOCK,
        ),
        producer="payment",
        correlation_id=uuid.UUID(order_id),
        occurred_at=datetime.now(UTC),
        event_id=event_id,
    )
    connection = pika.BlockingConnection(pika.URLParameters(broker_url()))
    try:
        channel = connection.channel()
        channel.confirm_delivery()
        channel.basic_publish(
            EXCHANGE,
            str(envelope.event_type),
            envelope.model_dump_json().encode(),
            properties=envelope_properties(envelope),
        )
    finally:
        connection.close()
    return envelope.event_id


# --- fixtures -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tap() -> Iterator[EventTap]:
    with EventTap(broker_url()) as event_tap:
        yield event_tap


@pytest.fixture(scope="module")
def shoppers() -> Iterator[list[Shopper]]:
    """Logged in once for the module: logins are rate limited at the gateway."""
    pool = [Shopper() for _ in range(3)]
    yield pool
    for customer in pool:
        customer.http.close()


@pytest.fixture
def shopper(shoppers: list[Shopper]) -> Shopper:
    return shoppers[0]


@pytest.fixture
def item(shopper: Shopper) -> tuple[str, str, int]:
    """(product slug, variant id, available) of an in-stock variant with a small stock."""
    found = shopper.http.get(
        "/api/search", params={"in_stock": "true", "sort": "newest", "page_size": 50}
    ).json()
    candidates: list[tuple[str, str, int]] = []
    for product in found["items"]:
        detail = shopper.http.get(f"/api/catalog/products/{product['slug']}/").json()
        candidates += [
            (product["slug"], v["id"], v["available"])
            for v in detail["variants"]
            if 3 <= v["available"] <= 60
        ]
        if len(candidates) >= 10:
            break
    assert candidates, "no in-stock variant with 3..60 units in the seed data"
    return random.choice(candidates)


# --- the six scenarios --------------------------------------------------------------------


def test_successful_order(shopper: Shopper, item: tuple[str, str, int], tap: EventTap) -> None:
    slug, variant_id, before = item
    order_id = shopper.checkout(variant_id, 2)

    reserved = shopper.wait_status(order_id, "RESERVED")
    assert reserved["reserved_until"] is not None
    assert available(shopper.http, slug, variant_id) == before - 2

    publish_payment(order_id, reserved["total_tiyin"])
    paid = shopper.wait_status(order_id, "PAID")
    assert all(group["sub_order_id"] for group in paid["sellers"])
    assert [h["to_status"] for h in paid["history"]] == ["PENDING", "RESERVED", "PAID"]

    order_paid = tap.wait_for(EventType.ORDER_PAID, order_id)
    assert order_paid.payload["sub_orders"]
    # Committed, not released: the units stay sold.
    time.sleep(1.5)
    assert available(shopper.http, slug, variant_id) == before - 2
    assert shopper.http.get("/api/cart/").json()["items_count"] == 0


def test_out_of_stock_race(
    shoppers: list[Shopper], item: tuple[str, str, int], tap: EventTap
) -> None:
    """Three shoppers pass the checkout pre-check for the whole stock; one wins."""
    slug, variant_id, before = item
    with ThreadPoolExecutor(len(shoppers)) as pool:
        orders = list(pool.map(lambda s: s.checkout(variant_id, before), shoppers))

    final = [
        s.wait_status(o, "RESERVED", "CANCELLED") for s, o in zip(shoppers, orders, strict=True)
    ]
    winners = [o for o in final if o["status"] == "RESERVED"]
    losers = [o for o in final if o["status"] == "CANCELLED"]
    assert len(winners) == 1 and len(losers) == 2
    assert {o["cancel_reason"] for o in losers} == {"OUT_OF_STOCK"}
    for loser in losers:
        failed = tap.wait_for(EventType.STOCK_FAILED, loser["id"])
        assert failed.payload["variant_ids"] == [variant_id]
    assert available(shoppers[0].http, slug, variant_id) == 0

    winner = shoppers[final.index(winners[0])]
    winner.cancel(winners[0]["id"])
    wait_available(winner.http, slug, variant_id, before)


def test_reservation_expires(shopper: Shopper, item: tuple[str, str, int], tap: EventTap) -> None:
    slug, variant_id, before = item
    order_id = shopper.checkout(variant_id, 1)
    shopper.wait_status(order_id, "RESERVED")

    expire_now(order_id)

    expired = shopper.wait_status(order_id, "EXPIRED")
    assert expired["history"][-1]["reason"] == "RESERVATION_EXPIRED"
    tap.wait_for(EventType.ORDER_EXPIRED, order_id)
    wait_available(shopper.http, slug, variant_id, before)


def test_late_payment_reserves_again(
    shopper: Shopper, item: tuple[str, str, int], tap: EventTap
) -> None:
    slug, variant_id, before = item
    order_id = shopper.checkout(variant_id, 1)
    total = shopper.wait_status(order_id, "RESERVED")["total_tiyin"]
    expire_now(order_id)
    shopper.wait_status(order_id, "EXPIRED")
    wait_available(shopper.http, slug, variant_id, before)

    publish_payment(order_id, total)

    paid = shopper.wait_status(order_id, "PAID")
    assert paid["late_payment"] is True
    retry = [e for e in tap.of(EventType.ORDER_CREATED, order_id) if e.payload["reserve_retry"]]
    assert len(retry) == 1
    tap.wait_for(EventType.ORDER_PAID, order_id)
    time.sleep(1.5)
    assert available(shopper.http, slug, variant_id) == before - 1


def test_late_payment_without_stock_is_refunded(
    shoppers: list[Shopper], item: tuple[str, str, int], tap: EventTap
) -> None:
    shopper, rival = shoppers[0], shoppers[1]
    slug, variant_id, before = item
    order_id = shopper.checkout(variant_id, 1)
    total = shopper.wait_status(order_id, "RESERVED")["total_tiyin"]
    expire_now(order_id)
    shopper.wait_status(order_id, "EXPIRED")
    wait_available(shopper.http, slug, variant_id, before)

    # Someone else takes every unit before the late payment arrives.
    rival_order = rival.checkout(variant_id, before)
    rival.wait_status(rival_order, "RESERVED")

    publish_payment(order_id, total)

    refunded = shopper.wait_status(order_id, "REFUNDED")
    assert refunded["late_payment"] is True
    assert refunded["history"][-1]["reason"] == "LATE_PAYMENT_OUT_OF_STOCK"
    refund = tap.wait_for(EventType.ORDER_REFUND_REQUESTED, order_id)
    assert refund.payload["amount_tiyin"] == total
    assert not tap.of(EventType.ORDER_PAID, order_id)

    rival.cancel(rival_order)
    wait_available(rival.http, slug, variant_id, before)


def test_repeated_payment_is_applied_once(
    shopper: Shopper, item: tuple[str, str, int], tap: EventTap
) -> None:
    slug, variant_id, before = item
    order_id = shopper.checkout(variant_id, 1)
    total = shopper.wait_status(order_id, "RESERVED")["total_tiyin"]

    # The same delivery twice (broker redelivery) and a second webhook with a new event.
    event_id = publish_payment(order_id, total)
    publish_payment(order_id, total, event_id=event_id)
    publish_payment(order_id, total)

    paid = shopper.wait_status(order_id, "PAID")
    time.sleep(3)  # let every copy reach the consumer
    assert [h["to_status"] for h in shopper.order(order_id)["history"]].count("PAID") == 1
    assert len(tap.of(EventType.ORDER_PAID, order_id)) == 1
    assert len({g["sub_order_id"] for g in paid["sellers"]}) == len(paid["sellers"])
    assert available(shopper.http, slug, variant_id) == before - 1


def test_dead_letter_queues_stay_empty() -> None:
    """Nothing in the scenarios above should have been parked for a human."""
    connection = pika.BlockingConnection(pika.URLParameters(broker_url()))
    try:
        channel = connection.channel()
        for service in ("catalog", "order", "search"):
            depth = channel.queue_declare(f"{service}.q.dlq", passive=True).method.message_count
            assert depth == 0, f"{service}.q.dlq has {depth} message(s)"
    finally:
        connection.close()


def test_events_are_valid_envelopes(tap: EventTap) -> None:
    """Every event the scenarios produced parses as its contract payload."""
    from contracts.events import parse_payload

    with tap._lock:
        events = list(tap._events)
    assert events
    for event in events:
        parse_payload(event)
        json.dumps(event.model_dump(mode="json"))
