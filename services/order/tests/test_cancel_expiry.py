"""Customer cancellation, lazy expiry on read, the scheduled expiry task and its command.

The order service only publishes order.cancelled / order.expired; the catalog releases
the stock when it consumes them, so no HTTP call to the catalog is expected here.
"""

from datetime import datetime, timedelta
from io import StringIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command
from django.utils import timezone
from rest_framework.test import APIClient

from config.celery import app as celery_app
from contracts.enums import EventType, OrderStatus
from contracts.events import OrderCancelled, OrderExpired
from messaging.models import Outbox
from orders import services
from orders.models import Order
from orders.tasks import expire_overdue_orders
from tests.conftest import FakeUpstream, outbox
from tests.factories import make_order

pytestmark = pytest.mark.django_db


def overdue() -> datetime:
    return timezone.now() - timedelta(minutes=1)


# --- cancel -----------------------------------------------------------------------------


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.RESERVED])
def test_customer_cancels_and_the_catalog_is_told(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID, status: OrderStatus
) -> None:
    order = make_order(customer_id=customer_id, status=status)

    response = api.post(f"/api/orders/{order.id}/cancel/")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["cancel_reason"] == "CANCELLED_BY_CUSTOMER"
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED.value
    [event] = outbox(EventType.ORDER_CANCELLED)
    payload = OrderCancelled.model_validate(event.payload)
    assert payload.order_id == order.id
    assert payload.reason == "CANCELLED_BY_CUSTOMER"
    assert [ref.variant_id for ref in payload.items] == [
        item.variant_id for item in order.items.order_by("variant_id")
    ]
    assert upstream.calls == []


@pytest.mark.parametrize("status", [OrderStatus.PAID, OrderStatus.CANCELLED, OrderStatus.EXPIRED])
def test_only_unpaid_orders_can_be_cancelled(
    api: APIClient, customer_id: UUID, status: OrderStatus
) -> None:
    order = make_order(customer_id=customer_id, status=status)

    response = api.post(f"/api/orders/{order.id}/cancel/")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert not Outbox.objects.exists()


def test_someone_elses_order_cannot_be_cancelled(other_api: APIClient) -> None:
    order = make_order()

    response = other_api.post(f"/api/orders/{order.id}/cancel/")

    assert response.status_code == 404
    order.refresh_from_db()
    assert order.status == OrderStatus.RESERVED.value


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
    [event] = outbox(EventType.ORDER_EXPIRED)
    assert OrderExpired.model_validate(event.payload).order_id == order.id
    assert upstream.calls == []


def test_listing_expires_overdue_orders(api: APIClient, customer_id: UUID) -> None:
    order = make_order(customer_id=customer_id, reserved_until=overdue())

    response = api.get("/api/orders/")

    assert response.json()["items"][0]["status"] == "EXPIRED"
    order.refresh_from_db()
    assert order.status == OrderStatus.EXPIRED.value


def test_orders_within_their_time_are_left_alone(api: APIClient, customer_id: UUID) -> None:
    order = make_order(customer_id=customer_id)

    assert api.get(f"/api/orders/{order.id}/status/").json()["status"] == "RESERVED"
    assert services.expire_order(order.id) is False
    assert not Outbox.objects.exists()


# --- scheduled expiry ---------------------------------------------------------------------


def test_task_expires_every_overdue_order() -> None:
    late = [make_order(reserved_until=overdue()) for _ in range(3)]
    on_time = make_order()
    pending = make_order(status=OrderStatus.PENDING)
    paid = make_order(status=OrderStatus.PAID, reserved_until=overdue())

    assert expire_overdue_orders() == 3

    for order in late:
        order.refresh_from_db()
        assert order.status == OrderStatus.EXPIRED.value
        assert order.history.last().reason == "RESERVATION_EXPIRED"  # type: ignore[union-attr]
    assert Order.objects.get(id=on_time.id).status == OrderStatus.RESERVED.value
    assert Order.objects.get(id=pending.id).status == OrderStatus.PENDING.value
    assert Order.objects.get(id=paid.id).status == OrderStatus.PAID.value
    events = outbox(EventType.ORDER_EXPIRED)
    assert {OrderExpired.model_validate(e.payload).order_id for e in events} == {
        order.id for order in late
    }
    assert expire_overdue_orders() == 0


def test_command_expires_in_batches() -> None:
    late = [make_order(reserved_until=overdue()) for _ in range(3)]
    out = StringIO()

    call_command("expire_orders", "--batch-size", "2", stdout=out)

    assert "expired 3 order(s)" in out.getvalue()
    assert {o.status for o in Order.objects.filter(id__in=[o.id for o in late])} == {"EXPIRED"}


def test_command_expires_one_order_before_its_deadline() -> None:
    target = make_order(reserved_until=timezone.now() + timedelta(minutes=10))
    other = make_order(reserved_until=timezone.now() + timedelta(minutes=10))
    out = StringIO()

    call_command("expire_orders", "--order", str(target.id), stdout=out)

    assert f"expired order {target.id}" in out.getvalue()
    assert Order.objects.get(id=target.id).status == OrderStatus.EXPIRED.value
    assert Order.objects.get(id=other.id).status == OrderStatus.RESERVED.value
    assert [
        OrderExpired.model_validate(e.payload).order_id for e in outbox(EventType.ORDER_EXPIRED)
    ] == [target.id]


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.PAID, OrderStatus.CANCELLED])
def test_command_refuses_orders_that_are_not_reserved(status: OrderStatus) -> None:
    order = make_order(status=status)
    with pytest.raises(CommandError, match="is not reserved"):
        call_command("expire_orders", "--order", str(order.id))
    assert Order.objects.get(id=order.id).status == status.value


def test_command_reports_an_unknown_order() -> None:
    order_id = uuid4()
    with pytest.raises(CommandError, match="not found"):
        call_command("expire_orders", "--order", str(order_id))


def test_beat_runs_the_expiry_task_every_30_seconds() -> None:
    [entry] = settings.CELERY_BEAT_SCHEDULE.values()

    assert entry["task"] == expire_overdue_orders.name == "orders.expire_overdue_orders"
    assert entry["schedule"] == 30.0
    options: Any = entry["options"]
    assert options["expires"] == 30.0


def test_celery_app_uses_its_own_queue_on_the_shared_broker() -> None:
    assert celery_app.main == "order"
    assert celery_app.conf.task_default_queue == "order"
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert "orders.expire_overdue_orders" in celery_app.tasks
