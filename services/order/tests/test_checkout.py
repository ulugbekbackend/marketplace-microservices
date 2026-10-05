"""Checkout: cart -> price snapshot -> PENDING order + order.created (reservation is async)."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from rest_framework.test import APIClient

from contracts.enums import EventType, OrderStatus
from contracts.events import OrderCreated
from messaging.models import Outbox
from orders import services
from orders.clients import CartLine
from orders.models import Order, OrderItem, OrderStatusHistory
from tests.conftest import ADDRESS, FakeUpstream, checkout, outbox

pytestmark = pytest.mark.django_db


def nothing_written() -> bool:
    return not (Order.objects.exists() or OrderItem.objects.exists() or Outbox.objects.exists())


def test_checkout_snapshots_the_catalog_and_asks_for_stock(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    seller_a, seller_b = uuid4(), uuid4()
    phone = upstream.add_variant(
        seller_id=seller_a, price_tiyin=500_000, title="Phone X", sku="PX-1", shop_name="A"
    )
    case = upstream.add_variant(
        seller_id=seller_b, price_tiyin=30_000, title="Case", sku="CS-1", image_url=None
    )
    upstream.put_in_cart(customer_id, phone, 2)
    upstream.put_in_cart(customer_id, case, 3)

    response = checkout(api)

    assert response.status_code == 202
    order = Order.objects.get()
    assert response.json() == {"order_id": str(order.id), "status": "PENDING"}
    assert order.customer_id == customer_id
    assert order.status == OrderStatus.PENDING.value
    assert order.total_tiyin == 2 * 500_000 + 3 * 30_000
    assert order.reserved_until is None
    assert order.late_payment is False
    assert order.delivery_address == {**ADDRESS, "notes": ""}

    items = {item.variant_id: item for item in order.items.all()}
    assert items[phone].title_snapshot == "Phone X"
    assert items[phone].sku_snapshot == "PX-1"
    assert items[phone].price_snapshot_tiyin == 500_000
    assert items[phone].seller_id == seller_a
    assert items[phone].shop_name_snapshot == "A"
    assert items[phone].image_snapshot.endswith("thumb.webp")
    assert items[phone].qty == 2
    assert items[phone].sub_order is None
    assert items[case].image_snapshot == ""
    assert items[case].qty == 3

    history = list(OrderStatusHistory.objects.filter(order=order).values_list("to_status"))
    assert history == [("PENDING",)]

    [created] = outbox(EventType.ORDER_CREATED)
    payload = OrderCreated.model_validate(created.payload)
    assert payload.order_id == order.id
    assert {(ref.variant_id, ref.qty) for ref in payload.items} == {(phone, 2), (case, 3)}
    assert payload.reserve_retry is False
    assert created.producer == "order"
    assert created.correlation_id == order.id
    assert Outbox.objects.count() == 1

    # Nothing is reserved over HTTP any more: the catalog answers order.created.
    assert [path for _, path in upstream.calls if "catalog" in path] == [
        "/internal/catalog/variants/bulk/"
    ]


def test_status_endpoint_shows_pending_until_the_catalog_answers(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    upstream.put_in_cart(customer_id, upstream.add_variant(), 1)
    order_id = checkout(api).json()["order_id"]

    body = api.get(f"/api/orders/{order_id}/status/").json()

    assert body == {"status": "PENDING", "reserved_until": None}


def test_prices_come_from_the_catalog_not_the_cart(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    variant = upstream.add_variant(price_tiyin=700_000)
    upstream.carts[customer_id] = [
        {"variant_id": str(variant), "qty": 1, "price_tiyin": 1}  # stale price is ignored
    ]

    assert checkout(api).status_code == 202

    assert Order.objects.get().total_tiyin == 700_000


def test_empty_cart_is_refused(api: APIClient) -> None:
    response = checkout(api)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CART_EMPTY"
    assert nothing_written()


def test_unavailable_items_are_listed_and_nothing_is_written(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    fine = upstream.add_variant(available=5)
    inactive = upstream.add_variant(is_active=False, available=4)
    short = upstream.add_variant(available=1)
    unknown = uuid4()
    for variant_id in (fine, inactive, short, unknown):
        upstream.put_in_cart(customer_id, variant_id, 2)

    response = checkout(api)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "ITEMS_UNAVAILABLE"
    assert error["details"]["items"] == [
        {"variant_id": str(inactive), "reason": "inactive", "available": 4},
        {"variant_id": str(short), "reason": "out_of_stock", "available": 1},
        {"variant_id": str(unknown), "reason": "not_found", "available": 0},
    ]
    assert nothing_written()


@pytest.mark.parametrize("which", ["cart_mode", "bulk_mode"])
@pytest.mark.parametrize("mode", ["down", "error"])
def test_unreachable_cart_or_catalog_is_503_and_nothing_is_written(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID, which: str, mode: str
) -> None:
    variant = upstream.add_variant()
    upstream.put_in_cart(customer_id, variant, 1)
    setattr(upstream, which, mode)

    response = checkout(api)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert nothing_written()


@pytest.mark.parametrize(
    "address",
    [
        {},
        {**ADDRESS, "phone": "call me"},
        {**ADDRESS, "street": ""},
        {**ADDRESS, "city": "x" * 101},
        {k: v for k, v in ADDRESS.items() if k != "full_name"},
    ],
)
def test_address_is_validated(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID, address: dict[str, str]
) -> None:
    upstream.put_in_cart(customer_id, upstream.add_variant(), 1)

    response = checkout(api, address=address)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert nothing_written()


def test_notes_are_kept(api: APIClient, upstream: FakeUpstream, customer_id: UUID) -> None:
    upstream.put_in_cart(customer_id, upstream.add_variant(), 1)

    checkout(api, address={**ADDRESS, "notes": "Ring twice"})

    assert Order.objects.get().delivery_address["notes"] == "Ring twice"


def test_checkout_needs_a_user(anonymous: APIClient) -> None:
    response = checkout(anonymous)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_outbox_row_shares_the_order_transaction(
    upstream: FakeUpstream, customer_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream.put_in_cart(customer_id, upstream.add_variant(), 1)

    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr(services, "add_to_outbox", broken)

    with pytest.raises(RuntimeError):
        services.checkout(customer_id, dict(ADDRESS))

    assert nothing_written()
    assert not OrderStatusHistory.objects.exists()


def test_repeated_cart_lines_are_merged() -> None:
    a, b = uuid4(), uuid4()

    merged = services.merge_lines([CartLine(a, 1), CartLine(b, 2), CartLine(a, 3), CartLine(b, 0)])

    assert merged == {a: 4, b: 2}
