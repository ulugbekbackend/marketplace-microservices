"""``/internal/orders/{id}/payable/``: what the payment service asks before charging."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from contracts.enums import OrderStatus
from tests.factories import make_order

pytestmark = pytest.mark.django_db


def payable(order_id: object) -> dict[str, object]:
    response = APIClient().get(f"/internal/orders/{order_id}/payable/")
    assert response.status_code == 200, response.content
    body: dict[str, object] = response.json()
    return body


def test_reserved_order_is_payable() -> None:
    order = make_order(lines=[(uuid4(), 150_000, 2)])

    body = payable(order.id)

    assert body["payable"] is True
    assert body["amount_tiyin"] == 300_000
    assert body["status"] == OrderStatus.RESERVED.value
    assert body["customer_id"] == str(order.customer_id)
    assert body["reserved_until"] is not None


def test_reservation_past_its_deadline_is_not_payable() -> None:
    order = make_order(reserved_until=timezone.now() - timedelta(seconds=1))

    assert payable(order.id)["payable"] is False


@pytest.mark.parametrize(
    "status",
    [
        OrderStatus.PENDING,
        OrderStatus.PAID,
        OrderStatus.EXPIRED,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    ],
)
def test_other_statuses_are_not_payable(status: OrderStatus) -> None:
    order = make_order(status=status)

    body = payable(order.id)

    assert body["payable"] is False
    assert body["status"] == status.value


def test_unknown_order_is_404() -> None:
    response = APIClient().get(f"/internal/orders/{uuid4()}/payable/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_internal_routes_are_not_in_the_public_schema() -> None:
    schema = APIClient().get("/api/orders/schema/?format=json").json()

    assert all(not path.startswith("/internal") for path in schema["paths"])
