"""Customer cancellation, lazy expiry on read and the expire_orders command."""

from datetime import datetime, timedelta
from io import StringIO
from uuid import UUID

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from contracts.enums import EventType, OrderStatus
from contracts.events import OrderCancelled, OrderExpired
from messaging.models import Outbox
from messaging.outbox import to_envelope
from orders import services
from orders.models import Order
from tests.conftest import FakeUpstream
from tests.factories import make_order

pytestmark = pytest.mark.django_db


def overdue() -> datetime:
    return timezone.now() - timedelta(minutes=1)


# --- cancel -----------------------------------------------------------------------------


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.RESERVED])
def test_customer_cancels_and_stock_is_released(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID, status: OrderStatus
) -> None:
    order = make_order(customer_id=customer_id, status=status)

    response = api.post(f"/api/orders/{order.id}/cancel/")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["cancel_reason"] == "CANCELLED_BY_CUSTOMER"
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED.value
    assert upstream.count("POST", f"/reservations/{order.id}/release/") == 1
    [row] = Outbox.objects.filter(event_type=EventType.ORDER_CANCELLED.value)
    payload = OrderCancelled.model_validate(to_envelope(row).payload)
    assert payload.order_id == order.id
    assert payload.reason == "CANCELLED_BY_CUSTOMER"
    assert [ref.variant_id for ref in payload.items] == [
        item.variant_id for item in order.items.all()
    ]


@pytest.mark.parametrize("status", [OrderStatus.PAID, OrderStatus.CANCELLED, OrderStatus.EXPIRED])
def test_only_unpaid_orders_can_be_cancelled(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID, status: OrderStatus
) -> None:
    order = make_order(customer_id=customer_id, status=status)

    response = api.post(f"/api/orders/{order.id}/cancel/")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert upstream.count("POST", "/release/") == 0
    assert not Outbox.objects.exists()


def test_someone_elses_order_cannot_be_cancelled(other_api: APIClient) -> None:
    order = make_order()

    response = other_api.post(f"/api/orders/{order.id}/cancel/")

    assert response.status_code == 404
    order.refresh_from_db()
    assert order.status == OrderStatus.RESERVED.value


def test_cancel_survives_a_failed_release(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    order = make_order(customer_id=customer_id)
    upstream.release_mode = "down"

    response = api.post(f"/api/orders/{order.id}/cancel/")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


# --- lazy expiry --------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", ["", "status/"])
def test_reading_an_overdue_order_expires_it(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID, suffix: str
) -> None:
    order = make_order(customer_id=customer_id, reserved_until=overdue())

    response = api.get(f"/api/orders/{order.id}/{suffix}")

    assert response.status_code == 200
    assert response.json()["status"] == "EXPIRED"
    order.refresh_from_db()
    assert order.status == OrderStatus.EXPIRED.value
    assert upstream.count("POST", f"/reservations/{order.id}/release/") == 1
    [row] = Outbox.objects.filter(event_type=EventType.ORDER_EXPIRED.value)
    assert OrderExpired.model_validate(to_envelope(row).payload).order_id == order.id


def test_listing_expires_overdue_orders(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    order = make_order(customer_id=customer_id, reserved_until=overdue())

    response = api.get("/api/orders/")

    assert response.json()["items"][0]["status"] == "EXPIRED"
    order.refresh_from_db()
    assert order.status == OrderStatus.EXPIRED.value


def test_orders_within_their_time_are_left_alone(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    order = make_order(customer_id=customer_id)

    assert api.get(f"/api/orders/{order.id}/status/").json()["status"] == "RESERVED"
    assert services.expire_order(order.id) is False
    assert upstream.count("POST", "/release/") == 0


# --- expire_orders command -----------------------------------------------------------------


def test_command_expires_every_overdue_order(upstream: FakeUpstream) -> None:
    late = [make_order(reserved_until=overdue()) for _ in range(3)]
    on_time = make_order()
    paid = make_order(status=OrderStatus.PAID)
    out = StringIO()

    call_command("expire_orders", "--batch-size", "2", stdout=out)

    assert "expired 3 order(s)" in out.getvalue()
    for order in late:
        order.refresh_from_db()
        assert order.status == OrderStatus.EXPIRED.value
    assert Order.objects.get(id=on_time.id).status == OrderStatus.RESERVED.value
    assert Order.objects.get(id=paid.id).status == OrderStatus.PAID.value
    assert Outbox.objects.filter(event_type=EventType.ORDER_EXPIRED.value).count() == 3
    assert upstream.count("POST", "/release/") == 3


def test_expiry_survives_a_failed_release(upstream: FakeUpstream) -> None:
    order = make_order(reserved_until=overdue())
    upstream.release_mode = "error"

    assert services.expire_overdue() == 1

    order.refresh_from_db()
    assert order.status == OrderStatus.EXPIRED.value
