"""Customer read endpoints: list, detail, status. Only the owner sees an order."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from contracts.enums import OrderStatus, UserRole
from orders.models import Order, SubOrder
from orders.state import lock_order, transition
from tests.conftest import user_client
from tests.factories import make_order

pytestmark = pytest.mark.django_db


def test_list_shows_own_orders_newest_first(api: APIClient, customer_id: UUID) -> None:
    older = make_order(customer_id=customer_id, lines=[(uuid4(), 100, 1), (uuid4(), 200, 2)])
    newer = make_order(customer_id=customer_id, status=OrderStatus.PAID)
    Order.objects.filter(id=older.id).update(created_at=timezone.now() - timedelta(days=1))
    make_order()  # someone else's

    response = api.get("/api/orders/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [str(newer.id), str(older.id)]
    assert body["items"][1] == {
        "id": str(older.id),
        "status": "RESERVED",
        "total_tiyin": 500,
        "items_count": 2,
        "reserved_until": body["items"][1]["reserved_until"],
        "created_at": body["items"][1]["created_at"],
    }


def test_list_is_paginated(api: APIClient, customer_id: UUID) -> None:
    for _ in range(5):
        make_order(customer_id=customer_id, status=OrderStatus.CANCELLED)

    body = api.get("/api/orders/", {"page": 2, "page_size": 2}).json()

    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_detail_groups_items_by_seller_and_shows_history(api: APIClient, customer_id: UUID) -> None:
    seller_a, seller_b = uuid4(), uuid4()
    order = make_order(
        customer_id=customer_id,
        lines=[(seller_a, 1_000, 2), (seller_b, 500, 1), (seller_a, 300, 1)],
    )

    response = api.get(f"/api/orders/{order.id}/")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(order.id)
    assert body["total_tiyin"] == 2_800
    assert body["delivery_address"]["city"] == "Toshkent"
    groups = {group["seller_id"]: group for group in body["sellers"]}
    assert groups[str(seller_a)]["subtotal_tiyin"] == 2_300
    assert groups[str(seller_a)]["sub_order_id"] is None
    assert groups[str(seller_a)]["status"] is None
    assert len(groups[str(seller_a)]["items"]) == 2
    item = groups[str(seller_b)]["items"][0]
    assert set(item) == {
        "id",
        "variant_id",
        "title",
        "sku",
        "image_url",
        "price_tiyin",
        "qty",
        "line_total_tiyin",
    }
    assert item["image_url"] is None
    assert item["line_total_tiyin"] == 500
    assert body["history"] == [
        {
            "from_status": None,
            "to_status": "RESERVED",
            "reason": "",
            "created_at": body["history"][0]["created_at"],
        }
    ]


def test_detail_shows_the_sub_order_after_payment(api: APIClient, customer_id: UUID) -> None:
    seller = uuid4()
    order = make_order(customer_id=customer_id, lines=[(seller, 1_000, 1)])
    with transaction.atomic():
        transition(lock_order(order.id), OrderStatus.PAID)
        sub_order = SubOrder.objects.create(order=order, seller_id=seller, subtotal_tiyin=1_000)
        order.items.update(sub_order=sub_order)

    body = api.get(f"/api/orders/{order.id}/").json()

    [group] = body["sellers"]
    assert group["sub_order_id"] == str(sub_order.id)
    assert group["status"] == "NEW"
    assert [h["to_status"] for h in body["history"]] == ["RESERVED", "PAID"]


def test_status_is_light(api: APIClient, customer_id: UUID) -> None:
    order = make_order(customer_id=customer_id)

    body = api.get(f"/api/orders/{order.id}/status/").json()

    assert set(body) == {"status", "reserved_until"}
    assert body["status"] == "RESERVED"


@pytest.mark.parametrize("suffix", ["", "status/"])
def test_other_users_get_404(other_api: APIClient, suffix: str) -> None:
    order = make_order()

    response = other_api.get(f"/api/orders/{order.id}/{suffix}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_order_is_404(api: APIClient) -> None:
    assert api.get(f"/api/orders/{uuid4()}/").status_code == 404


@pytest.mark.parametrize("url", ["/api/orders/", f"/api/orders/{uuid4()}/"])
def test_anonymous_gets_401(anonymous: APIClient, url: str) -> None:
    response = anonymous.get(url)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


def test_sellers_may_buy_too() -> None:
    seller_id = uuid4()
    make_order(customer_id=seller_id)

    body = user_client(seller_id, UserRole.SELLER).get("/api/orders/").json()

    assert body["total"] == 1


def test_openapi_schema_is_served(api: APIClient) -> None:
    response = api.get("/api/orders/schema/")

    assert response.status_code == 200
    assert b"orders_checkout" in response.content
    assert b"Idempotency-Key" in response.content
