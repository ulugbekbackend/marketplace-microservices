"""Internal API used by the cart, order and search services."""

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from contracts.enums import ProductStatus
from contracts.events import ProductUpdated
from products.documents import build_product_document
from tests.factories import (
    make_attribute_value,
    make_image,
    make_product,
    make_seller,
    make_variant,
)

pytestmark = pytest.mark.django_db

BULK = "/internal/catalog/variants/bulk/"
DOCUMENTS = "/internal/catalog/search-documents/"


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


# --- search documents ---------------------------------------------------------------------


def test_reserve_endpoints_are_gone(api: APIClient) -> None:
    order_id = uuid4()

    assert api.post("/internal/catalog/reservations/", {}, format="json").status_code == 404
    assert api.post(f"/internal/catalog/reservations/{order_id}/commit/").status_code == 404
    assert api.post(f"/internal/catalog/reservations/{order_id}/release/").status_code == 404


def test_search_documents_are_the_product_updated_payloads(api: APIClient) -> None:
    seller = make_seller(shop_name="Docs Shop")
    product = make_product(seller=seller, title="Indexed")
    variant = make_variant(product=product, price_tiyin=700, stock=3)
    variant.attribute_values.add(make_attribute_value(value="red"))
    make_image(product=product)

    response = api.get(DOCUMENTS)

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["page"], body["page_size"]) == (1, 1, 200)
    [item] = body["items"]
    assert ProductUpdated.model_validate(item) == build_product_document(product)
    assert item["product_id"] == str(product.id)
    assert item["shop_name"] == "Docs Shop"
    assert item["in_stock"] is True
    assert item["min_price_tiyin"] == 700


def test_search_documents_list_only_active_products_ordered_by_id(api: APIClient) -> None:
    active = [make_product() for _ in range(5)]
    for product in active:
        make_variant(product=product)
    make_product(status=ProductStatus.DRAFT.value)
    make_product(status=ProductStatus.ARCHIVED.value)
    expected = sorted(str(product.id) for product in active)

    first = api.get(DOCUMENTS, {"page": 1, "page_size": 2}).json()
    second = api.get(DOCUMENTS, {"page": 2, "page_size": 2}).json()
    last = api.get(DOCUMENTS, {"page": 3, "page_size": 2}).json()
    beyond = api.get(DOCUMENTS, {"page": 4, "page_size": 2}).json()

    assert first["total"] == 5
    ids = [item["product_id"] for page in (first, second, last) for item in page["items"]]
    assert ids == expected
    assert beyond["items"] == []
    assert (beyond["page"], beyond["page_size"], beyond["total"]) == (4, 2, 5)


def test_product_without_active_variants_is_out_of_stock_at_zero_price(api: APIClient) -> None:
    product = make_product()
    make_variant(product=product, is_active=False, price_tiyin=900)

    [item] = api.get(DOCUMENTS).json()["items"]

    assert item["product_id"] == str(product.id)
    assert (item["min_price_tiyin"], item["max_price_tiyin"]) == (0, 0)
    assert item["in_stock"] is False
    assert item["attributes"] == []
    assert item["image_url"] is None


@pytest.mark.parametrize(
    "query",
    [{"page": 0}, {"page_size": 0}, {"page_size": 501}, {"page": "x"}, {"page": 1_000_001}],
)
def test_search_documents_validate_paging(api: APIClient, query: dict[str, Any]) -> None:
    response = api.get(DOCUMENTS, query)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_search_documents_accept_the_largest_page(api: APIClient) -> None:
    make_variant()

    body = api.get(DOCUMENTS, {"page_size": 500}).json()

    assert (body["page_size"], len(body["items"])) == (500, 1)


def test_search_documents_query_count_does_not_grow_with_products(
    api: APIClient, django_assert_max_num_queries: Any
) -> None:
    category = make_product().category
    for _ in range(8):
        variant = make_variant(product=make_product(category=category))
        variant.attribute_values.add(make_attribute_value())
        make_image(product=variant.product)

    # count, products + sellers, variant stats, attributes, images,
    # categories, ancestors of the one category
    with django_assert_max_num_queries(7):
        body = api.get(DOCUMENTS).json()

    assert body["total"] == 9
    assert len(body["items"]) == 9
