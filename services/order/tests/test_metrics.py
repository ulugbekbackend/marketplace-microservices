"""checkout_total / checkout_failed_total: attempts, refusals and failed reservations."""

from uuid import UUID

import pytest
from prometheus_client import REGISTRY
from rest_framework.test import APIClient

from contracts.events import StockFailed
from orders import saga
from orders.models import Order
from tests.conftest import FakeUpstream, checkout, incoming

pytestmark = pytest.mark.django_db


def value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_a_checkout_is_counted(api: APIClient, upstream: FakeUpstream, customer_id: UUID) -> None:
    variant = upstream.add_variant()
    upstream.carts[customer_id] = [{"variant_id": str(variant), "qty": 1}]
    before = value("checkout_total")

    response = checkout(api)

    assert response.status_code == 202, response.content
    assert value("checkout_total") == before + 1


def test_an_empty_cart_is_counted_as_failed(api: APIClient, customer_id: UUID) -> None:
    before_total = value("checkout_total")
    before_failed = value("checkout_failed_total", reason="CART_EMPTY")

    assert checkout(api).status_code == 409

    assert value("checkout_total") == before_total + 1
    assert value("checkout_failed_total", reason="CART_EMPTY") == before_failed + 1


def test_a_failed_reservation_is_counted_with_its_reason(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    variant = upstream.add_variant()
    upstream.carts[customer_id] = [{"variant_id": str(variant), "qty": 1}]
    order = Order.objects.get(id=checkout(api).json()["order_id"])
    before = value("checkout_failed_total", reason="OUT_OF_STOCK")

    saga.on_stock_failed(incoming(StockFailed(order_id=order.id, reason="OUT_OF_STOCK")))

    assert value("checkout_failed_total", reason="OUT_OF_STOCK") == before + 1
