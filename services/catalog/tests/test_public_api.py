"""Storefront reads: no authentication, active data only."""

import pytest
from rest_framework.test import APIClient

from contracts.enums import ProductStatus
from products.models import Category, ImageStatus
from tests.factories import (
    make_attribute_value,
    make_image,
    make_product,
    make_seller,
    make_variant,
)

pytestmark = pytest.mark.django_db


def test_category_tree_is_nested_and_hides_inactive_branches(
    api: APIClient, categories: dict[str, Category]
) -> None:
    response = api.get("/api/catalog/categories/")

    assert response.status_code == 200
    tree = response.json()
    assert [node["slug"] for node in tree] == ["clothes", "electronics"]
    electronics = tree[1]
    assert set(electronics) == {"id", "name", "slug", "children"}
    assert [child["slug"] for child in electronics["children"]] == ["laptops", "phones"]
    phones = electronics["children"][1]
    assert [child["slug"] for child in phones["children"]] == ["smartphones"]
    assert phones["children"][0]["children"] == []


def test_list_shows_only_active_products_with_page_shape(
    api: APIClient, categories: dict[str, Category]
) -> None:
    active = make_product(category=categories["phones"])
    make_product(status=ProductStatus.DRAFT.value)
    make_product(status=ProductStatus.ARCHIVED.value)

    response = api.get("/api/catalog/products/")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [item["id"] for item in body["items"]] == [str(active.id)]


def test_list_pagination(api: APIClient) -> None:
    for _ in range(5):
        make_product()

    body = api.get("/api/catalog/products/?page=2&page_size=2").json()

    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_page_size_is_capped(api: APIClient) -> None:
    make_product()

    assert api.get("/api/catalog/products/?page_size=1000").json()["page_size"] == 100


def test_category_filter_includes_descendants(
    api: APIClient, categories: dict[str, Category]
) -> None:
    smartphone = make_product(category=categories["smartphones"])
    phone = make_product(category=categories["phones"])
    laptop = make_product(category=categories["laptops"])
    make_product(category=categories["clothes"])

    def ids(slug: str) -> set[str]:
        body = api.get(f"/api/catalog/products/?category={slug}").json()
        return {item["id"] for item in body["items"]}

    assert ids("electronics") == {str(smartphone.id), str(phone.id), str(laptop.id)}
    assert ids("phones") == {str(smartphone.id), str(phone.id)}
    assert ids("smartphones") == {str(smartphone.id)}
    assert ids("unknown") == set()
    assert ids("hidden") == set()


def test_seller_filter(api: APIClient) -> None:
    shop = make_seller(slug="best-shop")
    mine = make_product(seller=shop)
    make_product()

    body = api.get("/api/catalog/products/?seller=best-shop").json()

    assert [item["id"] for item in body["items"]] == [str(mine.id)]


def test_list_item_prices_stock_and_image(api: APIClient) -> None:
    product = make_product()
    make_variant(product=product, price_tiyin=500_000, stock=1, reserved=1)
    make_variant(product=product, price_tiyin=700_000, stock=0)
    make_variant(product=product, price_tiyin=100, stock=9, is_active=False)
    image = make_image(product=product)

    item = api.get("/api/catalog/products/").json()["items"][0]

    assert item["min_price_tiyin"] == 500_000
    assert item["max_price_tiyin"] == 700_000
    assert item["in_stock"] is False
    assert item["image_url"] == f"http://minio.localhost/catalog-test/{image.medium_key}"
    assert item["seller"]["slug"] == product.seller.slug
    assert item["category"]["slug"] == product.category.slug


def test_product_without_variants_has_null_prices(api: APIClient) -> None:
    make_product()

    item = api.get("/api/catalog/products/").json()["items"][0]

    assert item["min_price_tiyin"] is None
    assert item["max_price_tiyin"] is None
    assert item["in_stock"] is False
    assert item["image_url"] is None


def test_product_detail_shape(api: APIClient, categories: dict[str, Category]) -> None:
    product = make_product(category=categories["smartphones"], slug="galaxy-s25")
    red = make_attribute_value(attribute__code="color", attribute__name="Color", value="red")
    in_stock = make_variant(product=product, sku="S25-RED", price_tiyin=900, stock=3)
    in_stock.attribute_values.add(red)
    make_variant(product=product, sku="S25-BLK", price_tiyin=1_100, stock=2, reserved=2)
    make_variant(product=product, sku="S25-OFF", is_active=False)
    ready = make_image(product=product, position=1)
    make_image(product=product, position=0, status=ImageStatus.PROCESSING)
    make_image(product=product, position=2, status=ImageStatus.FAILED)

    response = api.get("/api/catalog/products/galaxy-s25/")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(product.id)
    assert body["title"] == product.title
    assert body["description"] == product.description
    assert body["min_price_tiyin"] == 900
    assert body["max_price_tiyin"] == 1_100
    assert body["in_stock"] is True
    assert [c["slug"] for c in body["breadcrumbs"]] == ["electronics", "phones", "smartphones"]
    assert body["seller"] == {
        "id": str(product.seller.id),
        "slug": product.seller.slug,
        "shop_name": product.seller.shop_name,
        "is_verified": True,
    }
    variants = {v["sku"]: v for v in body["variants"]}
    assert set(variants) == {"S25-RED", "S25-BLK"}
    assert variants["S25-RED"]["price_tiyin"] == 900
    assert variants["S25-RED"]["in_stock"] is True
    assert variants["S25-RED"]["available"] == 3
    assert variants["S25-BLK"]["in_stock"] is False
    assert variants["S25-BLK"]["available"] == 0  # all of it is reserved
    assert variants["S25-RED"]["attributes"] == [
        {"value_id": str(red.id), "code": "color", "name": "Color", "value": "red"}
    ]
    assert "stock" not in variants["S25-RED"]
    assert body["images"] == [
        {
            "id": str(ready.id),
            "position": 1,
            "thumb_url": f"http://minio.localhost/catalog-test/{ready.thumb_key}",
            "medium_url": f"http://minio.localhost/catalog-test/{ready.medium_key}",
            "large_url": f"http://minio.localhost/catalog-test/{ready.large_key}",
        }
    ]


@pytest.mark.parametrize("status", [ProductStatus.DRAFT.value, ProductStatus.ARCHIVED.value])
def test_inactive_product_detail_is_not_found(api: APIClient, status: str) -> None:
    make_product(slug="hidden-product", status=status)

    response = api.get("/api/catalog/products/hidden-product/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_shop_card_counts_active_products(api: APIClient) -> None:
    shop = make_seller(slug="chorsu", shop_name="Chorsu")
    make_product(seller=shop)
    make_product(seller=shop)
    make_product(seller=shop, status=ProductStatus.DRAFT.value)

    response = api.get("/api/catalog/shops/chorsu/")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(shop.id)
    assert body["shop_name"] == "Chorsu"
    assert body["product_count"] == 2
    assert api.get("/api/catalog/shops/nope/").status_code == 404


def test_malformed_identity_headers_are_rejected(api: APIClient) -> None:
    response = api.get("/api/catalog/products/", HTTP_X_USER_ID="not-a-uuid")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_openapi_schema_is_served(api: APIClient) -> None:
    response = api.get("/api/catalog/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/catalog/seller/variants/{variant_id}/stock/" in paths
    assert "/api/catalog/categories/" in paths
