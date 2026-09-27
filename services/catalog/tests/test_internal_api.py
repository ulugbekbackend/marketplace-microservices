"""Internal API used by the cart and order services."""

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from contracts.enums import ProductStatus
from tests.factories import (
    make_attribute_value,
    make_image,
    make_product,
    make_seller,
    make_variant,
)

pytestmark = pytest.mark.django_db

BULK = "/internal/catalog/variants/bulk/"
RESERVE = "/internal/catalog/reservations/"


def reservation_url(order_id: object, action: str) -> str:
    return f"{RESERVE}{order_id}/{action}/"


def test_bulk_returns_what_the_cart_and_order_need(api: APIClient) -> None:
    seller = make_seller(shop_name="Tech Shop", commission_rate=Decimal("0.0850"))
    product = make_product(seller=seller, title="Phone X")
    variant = make_variant(product=product, sku="PX-128", price_tiyin=500_000, stock=7, reserved=2)
    size = make_attribute_value(value="128 GB")
    variant.attribute_values.add(size)
    make_image(product=product, position=1)
    first = make_image(product=product, position=0)

    response = api.post(BULK, {"variant_ids": [str(variant.id)]}, format="json")

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert item == {
        "variant_id": str(variant.id),
        "product_id": str(product.id),
        "product_slug": product.slug,
        "title": "Phone X",
        "sku": "PX-128",
        "price_tiyin": 500_000,
        "available": 5,
        "is_active": True,
        "seller_id": str(seller.id),
        "shop_name": "Tech Shop",
        "commission_rate": "0.0850",
        "image_url": f"http://minio.localhost/catalog-test/{first.thumb_key}",
        "attributes": [
            {"code": size.attribute.code, "name": size.attribute.name, "value": "128 GB"}
        ],
    }


def test_bulk_skips_unknown_ids_and_flags_what_is_not_on_sale(api: APIClient) -> None:
    on_sale = make_variant()
    inactive = make_variant(is_active=False)
    archived = make_variant(product=make_product(status=ProductStatus.ARCHIVED.value))

    response = api.post(
        BULK,
        {"variant_ids": [str(v.id) for v in (on_sale, inactive, archived)] + [str(uuid4())]},
        format="json",
    )

    flags = {item["variant_id"]: item["is_active"] for item in response.json()["items"]}
    assert flags == {str(on_sale.id): True, str(inactive.id): False, str(archived.id): False}


def test_bulk_validates_input(api: APIClient) -> None:
    bad = api.post(BULK, {"variant_ids": ["nope"]}, format="json")
    too_many = api.post(BULK, {"variant_ids": [str(uuid4()) for _ in range(201)]}, format="json")
    empty = api.post(BULK, {"variant_ids": []}, format="json")

    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert too_many.status_code == 400
    assert empty.json() == {"items": []}


def test_bulk_query_count_does_not_grow_with_variants(
    api: APIClient,
    django_assert_max_num_queries: Any,
) -> None:
    ids = []
    for _ in range(5):
        variant = make_variant()
        variant.attribute_values.add(make_attribute_value())
        make_image(product=variant.product)
        ids.append(str(variant.id))

    with django_assert_max_num_queries(4):
        response = api.post(BULK, {"variant_ids": ids}, format="json")

    assert len(response.json()["items"]) == 5


def test_reserve_commit_and_release_over_http(api: APIClient) -> None:
    variant = make_variant(stock=5)
    order_id = uuid4()
    body = {"order_id": str(order_id), "items": [{"variant_id": str(variant.id), "qty": 2}]}

    reserved = api.post(RESERVE, body, format="json")
    committed = api.post(reservation_url(order_id, "commit"))
    released = api.post(reservation_url(order_id, "release"))

    assert reserved.status_code == 200
    assert reserved.json()["status"] == "active"
    assert reserved.json()["items"] == [{"variant_id": str(variant.id), "qty": 2}]
    assert reserved.json()["expires_at"]
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"
    assert released.json()["items"] == []  # nothing active to give back
    variant.refresh_from_db()
    assert (variant.stock, variant.reserved) == (3, 0)


def test_reserve_out_of_stock_is_409_with_the_variants(api: APIClient) -> None:
    variant = make_variant(stock=1)
    body = {"order_id": str(uuid4()), "items": [{"variant_id": str(variant.id), "qty": 2}]}

    response = api.post(RESERVE, body, format="json")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "OUT_OF_STOCK"
    assert error["details"] == {"variant_ids": [str(variant.id)]}


def test_reserve_validates_input(api: APIClient) -> None:
    no_items = api.post(RESERVE, {"order_id": str(uuid4()), "items": []}, format="json")
    zero = api.post(
        RESERVE,
        {"order_id": str(uuid4()), "items": [{"variant_id": str(uuid4()), "qty": 0}]},
        format="json",
    )

    assert no_items.status_code == 400
    assert zero.status_code == 400


def test_commit_of_an_unknown_order_is_409(api: APIClient) -> None:
    response = api.post(reservation_url(uuid4(), "commit"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_RESERVED"


def test_internal_routes_are_not_in_the_public_schema(api: APIClient) -> None:
    schema = api.get("/api/catalog/schema/?format=json").json()

    assert all(not path.startswith("/internal") for path in schema["paths"])


def test_stock_cannot_drop_below_reserved_units(seller_api: APIClient, seller) -> None:  # type: ignore[no-untyped-def]
    from products import reservations

    variant = make_variant(product=make_product(seller=seller), stock=5)
    reservations.reserve(uuid4(), [reservations.ReservationItem(variant.id, 4)])

    response = seller_api.patch(
        f"/api/catalog/seller/variants/{variant.id}/stock/", {"stock": 3}, format="json"
    )

    assert response.status_code == 409
