"""Seller read endpoints: the sub-order list with filters, the detail and access rules."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from rest_framework.test import APIClient

from contracts.enums import OrderStatus, SubOrderStatus, UserRole
from tests.conftest import user_client
from tests.factories import make_paid_order, make_sub_order

pytestmark = pytest.mark.django_db

LIST = "/api/orders/seller/"


@pytest.fixture
def seller_id() -> UUID:
    return uuid4()


@pytest.fixture
def seller_api(seller_id: UUID) -> APIClient:
    return user_client(seller_id, UserRole.SELLER)


def ids(body: dict[str, Any]) -> list[str]:
    return [item["id"] for item in body["items"]]


def utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def test_list_shows_own_sub_orders_newest_first(seller_api: APIClient, seller_id: UUID) -> None:
    other_seller = uuid4()
    order, subs = make_paid_order(
        lines=[(seller_id, 150_000, 2), (seller_id, 50_000, 3), (other_seller, 10_000, 1)]
    )
    mine = subs[seller_id]
    older = make_sub_order(seller_id, created_at=utc(2026, 1, 1, 12))

    response = seller_api.get(LIST)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert ids(body) == [str(mine.id), str(older.id)]
    assert body["items"][0] == {
        "id": str(mine.id),
        "order_id": str(order.id),
        "status": "NEW",
        "subtotal_tiyin": 450_000,
        "commission_tiyin": 45_000,
        "net_tiyin": 405_000,
        "items_count": 5,
        "created_at": body["items"][0]["created_at"],
        "updated_at": body["items"][0]["updated_at"],
        "customer_name": "Aziz Karimov",
        "city": "Toshkent",
    }


def test_list_filters_by_status_repeated_or_comma_separated(
    seller_api: APIClient, seller_id: UUID
) -> None:
    new = make_sub_order(seller_id)
    accepted = make_sub_order(seller_id, status=SubOrderStatus.ACCEPTED)
    shipped = make_sub_order(
        seller_id, status=SubOrderStatus.SHIPPED, order_status=OrderStatus.FULFILLING
    )

    repeated = seller_api.get(LIST, {"status": ["NEW", "SHIPPED"]}).json()
    comma = seller_api.get(f"{LIST}?status=ACCEPTED,SHIPPED").json()
    single = seller_api.get(LIST, {"status": "ACCEPTED"}).json()

    assert set(ids(repeated)) == {str(new.id), str(shipped.id)}
    assert set(ids(comma)) == {str(accepted.id), str(shipped.id)}
    assert ids(single) == [str(accepted.id)]


def test_list_filters_by_tashkent_days_inclusive(seller_api: APIClient, seller_id: UUID) -> None:
    # Tashkent is UTC+5: 1 March starts at 28 Feb 19:00 UTC.
    before = make_sub_order(seller_id, created_at=utc(2026, 2, 28, 18, 59, 59))
    first = make_sub_order(seller_id, created_at=utc(2026, 2, 28, 19, 0))
    last = make_sub_order(seller_id, created_at=utc(2026, 3, 2, 18, 59, 59))
    after = make_sub_order(seller_id, created_at=utc(2026, 3, 2, 19, 0))

    both = seller_api.get(LIST, {"date_from": "2026-03-01", "date_to": "2026-03-02"}).json()
    since = seller_api.get(LIST, {"date_from": "2026-03-01"}).json()
    until = seller_api.get(LIST, {"date_to": "2026-02-28"}).json()

    assert ids(both) == [str(last.id), str(first.id)]
    assert ids(since) == [str(after.id), str(last.id), str(first.id)]
    assert ids(until) == [str(before.id)]


@pytest.mark.parametrize(
    "params",
    [
        {"status": "LOST"},
        {"status": "NEW,LOST"},
        {"date_from": "yesterday"},
        {"date_from": "2026-03-02", "date_to": "2026-03-01"},
    ],
)
def test_bad_filters_are_400(seller_api: APIClient, params: dict[str, str]) -> None:
    response = seller_api.get(LIST, params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_is_paginated(seller_api: APIClient, seller_id: UUID) -> None:
    for _ in range(5):
        make_sub_order(seller_id)

    body = seller_api.get(LIST, {"page": 2, "page_size": 2}).json()

    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_list_query_count_does_not_grow(
    seller_api: APIClient, seller_id: UUID, django_assert_num_queries: Any
) -> None:
    make_paid_order(lines=[(seller_id, 100, 1), (seller_id, 200, 2), (uuid4(), 5, 1)])

    with django_assert_num_queries(2):  # count + page
        assert seller_api.get(LIST).json()["total"] == 1

    for _ in range(6):
        make_paid_order(lines=[(seller_id, 100, 1), (seller_id, 200, 2)])
    with django_assert_num_queries(2):
        assert seller_api.get(LIST).json()["total"] == 7


def test_detail_has_everything_to_ship(seller_api: APIClient, seller_id: UUID) -> None:
    order, subs = make_paid_order(lines=[(seller_id, 150_000, 2), (uuid4(), 10_000, 1)])
    sub_order = subs[seller_id]
    item = order.items.get(seller_id=seller_id)
    item.image_snapshot = "http://minio.localhost/marketplace/a.webp"
    item.save()

    response = seller_api.get(f"{LIST}{sub_order.id}/")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(sub_order.id)
    assert body["order_status"] == "PAID"
    assert body["commission_rate"] == "0.1000"
    assert body["net_tiyin"] == 270_000
    assert body["items_count"] == 2
    assert body["tracking_number"] == ""
    assert body["cancel_reason"] == ""
    assert body["delivery_address"]["phone"] == "+998901234567"
    assert body["delivery_address"]["full_name"] == "Aziz Karimov"
    assert body["items"] == [
        {
            "id": str(item.id),
            "variant_id": str(item.variant_id),
            "title": item.title_snapshot,
            "sku": item.sku_snapshot,
            "image": "http://minio.localhost/marketplace/a.webp",
            "price_tiyin": 150_000,
            "qty": 2,
            "line_total_tiyin": 300_000,
        }
    ]
    assert body["history"] == [
        {
            "from_status": None,
            "to_status": "NEW",
            "reason": "",
            "created_at": body["history"][0]["created_at"],
        }
    ]


def test_detail_of_foreign_sub_order_is_404(seller_api: APIClient) -> None:
    sub_order = make_sub_order(uuid4())

    response = seller_api.get(f"{LIST}{sub_order.id}/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_seller_id_header_is_used_when_present(seller_id: UUID) -> None:
    sub_order = make_sub_order(seller_id)
    client = APIClient()
    client.credentials(
        HTTP_X_USER_ID=str(seller_id),
        HTTP_X_USER_ROLE="seller",
        HTTP_X_SELLER_ID=str(seller_id),
    )

    assert client.get(f"{LIST}{sub_order.id}/").status_code == 200


SELLER_URLS = [LIST, f"{LIST}stats/", f"{LIST}{uuid4()}/"]


@pytest.mark.parametrize("url", SELLER_URLS)
@pytest.mark.parametrize("role", [UserRole.CUSTOMER, UserRole.ADMIN])
def test_other_roles_are_403(url: str, role: UserRole) -> None:
    response = user_client(uuid4(), role).get(url)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("url", SELLER_URLS)
def test_anonymous_is_401(anonymous: APIClient, url: str) -> None:
    response = anonymous.get(url)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


def test_schema_lists_the_seller_routes(seller_api: APIClient) -> None:
    content = seller_api.get("/api/orders/schema/").content

    for operation in (
        b"seller_orders_list",
        b"seller_orders_retrieve",
        b"seller_orders_set_status",
        b"seller_orders_stats",
        b"SubOrderTargetStatusEnum",
    ):
        assert operation in content
