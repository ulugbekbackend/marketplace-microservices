"""Mock payment endpoint: the same path as a ``payment.paid`` event (split, commission)."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from contracts.enums import EventType, OrderStatus, PaymentProvider, SubOrderStatus
from contracts.events import OrderPaid, PaymentPaid, StockReserved
from orders import saga
from orders.models import Order, SubOrder
from tests.conftest import FakeUpstream, checkout, incoming, outbox
from tests.factories import make_order

pytestmark = pytest.mark.django_db


def pay(client: APIClient, order_id: object) -> Any:
    return client.post(f"/api/orders/{order_id}/pay/mock/")


def reserve(order: Order) -> None:
    """The catalog's answer to order.created."""
    saga.on_stock_reserved(
        incoming(
            StockReserved(order_id=order.id, expires_at=timezone.now() + timedelta(minutes=15))
        )
    )


@pytest.fixture
def two_seller_order(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> tuple[Order, UUID, UUID]:
    """Seller A: 2 x 1 000 005 at 10 %; seller B: 1 x 333 333 + 3 x 1 at 8.5 %. RESERVED."""
    seller_a, seller_b = sorted([uuid4(), uuid4()])
    a1 = upstream.add_variant(seller_id=seller_a, price_tiyin=1_000_005, commission_rate="0.1000")
    b1 = upstream.add_variant(seller_id=seller_b, price_tiyin=333_333, commission_rate="0.0850")
    b2 = upstream.add_variant(seller_id=seller_b, price_tiyin=1, commission_rate="0.0850")
    upstream.put_in_cart(customer_id, a1, 2)
    upstream.put_in_cart(customer_id, b1, 1)
    upstream.put_in_cart(customer_id, b2, 3)
    assert checkout(api).status_code == 202
    order = Order.objects.get()
    reserve(order)
    order.refresh_from_db()
    assert order.status == OrderStatus.RESERVED.value
    return order, seller_a, seller_b


@pytest.mark.usefixtures("mock_payments")
def test_mock_pay_splits_the_order_per_seller(
    api: APIClient,
    upstream: FakeUpstream,
    customer_id: UUID,
    two_seller_order: tuple[Order, UUID, UUID],
) -> None:
    order, seller_a, seller_b = two_seller_order

    response = pay(api, order.id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PAID"
    assert body["late_payment"] is False
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID.value

    a = SubOrder.objects.get(order=order, seller_id=seller_a)
    b = SubOrder.objects.get(order=order, seller_id=seller_b)
    assert a.status == b.status == SubOrderStatus.NEW.value
    assert a.subtotal_tiyin == 2_000_010
    assert a.commission_rate_snapshot == Decimal("0.1000")
    assert a.commission_tiyin == 200_001  # 200 001.0
    assert b.subtotal_tiyin == 333_336
    assert b.commission_rate_snapshot == Decimal("0.0850")
    assert b.commission_tiyin == 28_334  # 28 333.56 rounds up
    assert {item.sub_order_id for item in order.items.filter(seller_id=seller_a)} == {a.id}
    assert {item.sub_order_id for item in order.items.filter(seller_id=seller_b)} == {b.id}

    groups = {group["seller_id"]: group for group in body["sellers"]}
    assert groups[str(seller_a)]["sub_order_id"] == str(a.id)
    assert groups[str(seller_a)]["status"] == "NEW"
    assert groups[str(seller_a)]["tracking_number"] == ""
    assert groups[str(seller_a)]["cancel_reason"] == ""
    assert [(h["from_status"], h["to_status"]) for h in groups[str(seller_a)]["history"]] == [
        (None, "NEW")
    ]
    assert groups[str(seller_b)]["subtotal_tiyin"] == 333_336
    assert [(h.from_status, h.to_status) for h in b.history.all()] == [(None, "NEW")]
    assert [h["to_status"] for h in body["history"]] == ["PENDING", "RESERVED", "PAID"]

    [event] = outbox(EventType.ORDER_PAID)
    paid = OrderPaid.model_validate(event.payload)
    assert paid.order_id == order.id
    assert paid.customer_id == customer_id
    assert [(ref.id, ref.seller_id) for ref in paid.sub_orders] == [
        (a.id, seller_a),
        (b.id, seller_b),
    ]
    assert paid.sub_orders[1].commission_tiyin == 28_334
    assert {(item.qty) for item in paid.sub_orders[1].items} == {1, 3}

    # The catalog commits the stock from order.paid; no HTTP call for it.
    assert upstream.count("POST", "/reservations/") == 0
    assert upstream.count("DELETE", f"/internal/cart/{customer_id}") == 1
    assert customer_id not in upstream.carts


@pytest.mark.usefixtures("mock_payments")
def test_mock_pay_goes_through_the_payment_event_path(
    api: APIClient, monkeypatch: pytest.MonkeyPatch, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    seen: list[PaymentPaid] = []
    real = saga.apply_payment

    def spy(payment: PaymentPaid, **kwargs: Any) -> Order:
        seen.append(payment)
        return real(payment, **kwargs)

    monkeypatch.setattr(saga, "apply_payment", spy)

    assert pay(api, order.id).status_code == 200

    [payment] = seen
    assert payment.order_id == order.id
    assert payment.provider is PaymentProvider.MOCK
    assert payment.amount_tiyin == order.total_tiyin


def test_half_tiyin_commission_rounds_half_up(
    upstream: FakeUpstream, customer_id: UUID, mock_payments: None, api: APIClient
) -> None:
    variant = upstream.add_variant(price_tiyin=1_000_005, commission_rate="0.1000")
    upstream.put_in_cart(customer_id, variant, 1)
    checkout(api)
    order = Order.objects.get()
    reserve(order)

    saga.mock_pay(Order.objects.get())

    assert SubOrder.objects.get().commission_tiyin == 100_001  # 100 000.5 -> 100 001


@pytest.mark.usefixtures("mock_payments")
def test_commission_uses_the_current_rate(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, seller_a, _ = two_seller_order
    for info in upstream.variants.values():
        if info["seller_id"] == str(seller_a):
            info["commission_rate"] = "0.1500"

    pay(api, order.id)

    assert SubOrder.objects.get(seller_id=seller_a).commission_rate_snapshot == Decimal("0.1500")


@pytest.mark.usefixtures("mock_payments")
def test_paying_twice_is_idempotent(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    first = pay(api, order.id)
    bulk_calls = upstream.count("POST", "/variants/bulk/")

    second = pay(api, order.id)

    assert second.status_code == 200
    assert second.json() == first.json()
    assert SubOrder.objects.count() == 2
    assert len(outbox(EventType.ORDER_PAID)) == 1
    assert upstream.count("POST", "/variants/bulk/") == bulk_calls  # no rates for a paid order


def test_mock_pay_is_hidden_when_the_flag_is_off(
    api: APIClient, settings: Any, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    settings.DEBUG = True
    settings.PAYMENT_MOCK_ENABLED = False

    response = pay(api, order.id)

    assert response.status_code == 404
    order.refresh_from_db()
    assert order.status == OrderStatus.RESERVED.value


def test_mock_pay_is_hidden_outside_debug(
    api: APIClient, settings: Any, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    settings.DEBUG = False
    settings.PAYMENT_MOCK_ENABLED = True

    assert pay(api, order.id).status_code == 404


@pytest.mark.usefixtures("mock_payments")
def test_only_the_owner_can_pay(
    other_api: APIClient, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order

    response = pay(other_api, order.id)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.usefixtures("mock_payments")
def test_pending_order_cannot_be_paid_yet(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    upstream.put_in_cart(customer_id, upstream.add_variant(), 1)
    order_id = checkout(api).json()["order_id"]

    response = pay(api, order_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_RESERVED"
    assert Order.objects.get().status == OrderStatus.PENDING.value
    assert outbox(EventType.ORDER_PAID) == []


@pytest.mark.parametrize("status", [OrderStatus.CANCELLED, OrderStatus.REFUNDED])
@pytest.mark.usefixtures("mock_payments")
def test_cancelled_or_refunded_order_cannot_be_paid(
    api: APIClient, customer_id: UUID, status: OrderStatus
) -> None:
    order = make_order(customer_id=customer_id, status=status)

    response = pay(api, order.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert outbox(EventType.ORDER_REFUND_REQUESTED) == []


@pytest.mark.usefixtures("mock_payments")
def test_overdue_order_is_expired_instead_of_paid(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    Order.objects.filter(id=order.id).update(reserved_until=timezone.now() - timedelta(seconds=1))

    response = pay(api, order.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_EXPIRED"
    order.refresh_from_db()
    assert order.status == OrderStatus.EXPIRED.value
    assert order.late_payment is False
    assert len(outbox(EventType.ORDER_EXPIRED)) == 1
    assert outbox(EventType.ORDER_CREATED)[-1].payload["reserve_retry"] is False

    again = pay(api, order.id)
    assert again.json()["error"]["code"] == "ORDER_EXPIRED"


@pytest.mark.parametrize("mode", ["down", "error"])
@pytest.mark.usefixtures("mock_payments")
def test_catalog_down_keeps_the_order_reserved(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID], mode: str
) -> None:
    order, _, _ = two_seller_order
    upstream.bulk_mode = mode

    response = pay(api, order.id)

    assert response.status_code == 503
    order.refresh_from_db()
    assert order.status == OrderStatus.RESERVED.value
    assert not SubOrder.objects.exists()


@pytest.mark.usefixtures("mock_payments")
def test_unknown_commission_rate_is_503(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, seller_a, _ = two_seller_order
    for variant_id, info in list(upstream.variants.items()):
        if info["seller_id"] == str(seller_a):
            del upstream.variants[variant_id]

    response = pay(api, order.id)

    assert response.status_code == 503
    assert Order.objects.get(id=order.id).status == OrderStatus.RESERVED.value


@pytest.mark.usefixtures("mock_payments")
def test_cart_clear_failure_does_not_fail_the_payment(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    upstream.clear_mode = "down"

    response = pay(api, order.id)

    assert response.status_code == 200
    assert response.json()["status"] == "PAID"
