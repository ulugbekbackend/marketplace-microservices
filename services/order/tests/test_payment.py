"""Mock payment and the ``mark_paid`` use case: commit, split per seller, commission."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from contracts.enums import EventType, OrderStatus, SubOrderStatus
from contracts.events import OrderPaid
from messaging.models import Outbox
from messaging.outbox import to_envelope
from orders import services
from orders.models import Order, SubOrder
from tests.conftest import FakeUpstream, checkout
from tests.factories import make_order

pytestmark = pytest.mark.django_db


def pay(client: APIClient, order_id: object) -> Any:
    return client.post(f"/api/orders/{order_id}/pay/mock/")


@pytest.fixture
def two_seller_order(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> tuple[Order, UUID, UUID]:
    """Seller A: 2 x 1 000 005 at 10 %; seller B: 1 x 333 333 + 3 x 1 at 8.5 %."""
    seller_a, seller_b = sorted([uuid4(), uuid4()])
    a1 = upstream.add_variant(seller_id=seller_a, price_tiyin=1_000_005, commission_rate="0.1000")
    b1 = upstream.add_variant(seller_id=seller_b, price_tiyin=333_333, commission_rate="0.0850")
    b2 = upstream.add_variant(seller_id=seller_b, price_tiyin=1, commission_rate="0.0850")
    upstream.put_in_cart(customer_id, a1, 2)
    upstream.put_in_cart(customer_id, b1, 1)
    upstream.put_in_cart(customer_id, b2, 3)
    assert checkout(api).status_code == 202
    return Order.objects.get(), seller_a, seller_b


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

    [row] = Outbox.objects.filter(event_type=EventType.ORDER_PAID.value)
    paid = OrderPaid.model_validate(to_envelope(row).payload)
    assert paid.order_id == order.id
    assert paid.customer_id == customer_id
    assert [(ref.id, ref.seller_id) for ref in paid.sub_orders] == [
        (a.id, seller_a),
        (b.id, seller_b),
    ]
    assert paid.sub_orders[1].commission_tiyin == 28_334
    assert {(item.qty) for item in paid.sub_orders[1].items} == {1, 3}

    assert upstream.count("POST", f"/reservations/{order.id}/commit/") == 1
    assert upstream.count("DELETE", f"/internal/cart/{customer_id}") == 1
    assert customer_id not in upstream.carts


def test_half_tiyin_commission_rounds_half_up(
    upstream: FakeUpstream, customer_id: UUID, mock_payments: None, api: APIClient
) -> None:
    variant = upstream.add_variant(price_tiyin=1_000_005, commission_rate="0.1000")
    upstream.put_in_cart(customer_id, variant, 1)
    checkout(api)
    order = Order.objects.get()

    services.mark_paid(order.id)

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

    second = pay(api, order.id)

    assert second.status_code == 200
    assert second.json() == first.json()
    assert upstream.count("POST", "/commit/") == 1
    assert SubOrder.objects.count() == 2
    assert Outbox.objects.filter(event_type=EventType.ORDER_PAID.value).count() == 1


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
def test_cancelled_order_cannot_be_paid(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    services.cancel_order(order.id)

    response = pay(api, order.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert upstream.count("POST", "/commit/") == 0


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
    assert upstream.count("POST", f"/reservations/{order.id}/release/") == 1
    assert upstream.count("POST", "/commit/") == 0

    again = pay(api, order.id)
    assert again.json()["error"]["code"] == "ORDER_EXPIRED"


@pytest.mark.usefixtures("mock_payments")
def test_catalog_without_reservation_is_409(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    upstream.commit_mode = "not_reserved"

    response = pay(api, order.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_RESERVED"
    order.refresh_from_db()
    assert order.status == OrderStatus.RESERVED.value


@pytest.mark.parametrize("which", ["commit_mode", "bulk_mode"])
@pytest.mark.usefixtures("mock_payments")
def test_catalog_down_keeps_the_order_reserved(
    api: APIClient,
    upstream: FakeUpstream,
    two_seller_order: tuple[Order, UUID, UUID],
    which: str,
) -> None:
    order, _, _ = two_seller_order
    setattr(upstream, which, "down")

    response = pay(api, order.id)

    assert response.status_code == 503
    order.refresh_from_db()
    assert order.status == OrderStatus.RESERVED.value
    assert not SubOrder.objects.exists()


@pytest.mark.usefixtures("mock_payments")
def test_unknown_commission_rate_is_503_before_commit(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, seller_a, _ = two_seller_order
    for variant_id, info in list(upstream.variants.items()):
        if info["seller_id"] == str(seller_a):
            del upstream.variants[variant_id]

    response = pay(api, order.id)

    assert response.status_code == 503
    assert upstream.count("POST", "/commit/") == 0


@pytest.mark.usefixtures("mock_payments")
def test_cart_clear_failure_does_not_fail_the_payment(
    api: APIClient, upstream: FakeUpstream, two_seller_order: tuple[Order, UUID, UUID]
) -> None:
    order, _, _ = two_seller_order
    upstream.clear_mode = "down"

    response = pay(api, order.id)

    assert response.status_code == 200
    assert response.json()["status"] == "PAID"


def test_late_payment_path_accepts_an_expired_order(upstream: FakeUpstream) -> None:
    order = make_order(status=OrderStatus.EXPIRED)
    for item in order.items.all():
        upstream.variants[item.variant_id] = {
            **upstream.variants[upstream.add_variant(seller_id=item.seller_id)],
            "variant_id": str(item.variant_id),
        }

    paid = services.mark_paid(order.id, allow_expired=True)

    assert paid.status == OrderStatus.PAID.value
    assert SubOrder.objects.filter(order=order).count() == 1
