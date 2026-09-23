"""Seller cabinet: own products only, errors in the shared shape."""

from typing import Any
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from contracts.enums import ProductStatus, UserRole
from messaging.models import Outbox
from products.models import AttributeValue, Category, Product, ProductVariant
from sellers.models import Seller
from tests.factories import make_product, make_variant

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/catalog/seller/products/"


def product_url(product_id: Any) -> str:
    return f"{PRODUCTS}{product_id}/"


def variant_url(variant_id: Any) -> str:
    return f"/api/catalog/seller/variants/{variant_id}/"


# --- access ---------------------------------------------------------------------------


SELLER_ENDPOINTS = [
    ("get", PRODUCTS),
    ("post", PRODUCTS),
    ("get", f"{PRODUCTS}{uuid4()}/"),
    ("patch", f"{PRODUCTS}{uuid4()}/"),
    ("delete", f"{PRODUCTS}{uuid4()}/"),
    ("post", f"{PRODUCTS}{uuid4()}/variants/"),
    ("post", f"{PRODUCTS}{uuid4()}/images/"),
    ("patch", f"/api/catalog/seller/variants/{uuid4()}/"),
    ("patch", f"/api/catalog/seller/variants/{uuid4()}/stock/"),
    ("post", "/api/catalog/seller/uploads/presign/"),
    ("get", "/api/catalog/attributes/"),
]


@pytest.mark.parametrize(("method", "url"), SELLER_ENDPOINTS)
def test_anonymous_gets_401(api: APIClient, method: str, url: str) -> None:
    response = getattr(api, method)(url)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.parametrize("role", [UserRole.CUSTOMER, UserRole.ADMIN])
@pytest.mark.parametrize(("method", "url"), SELLER_ENDPOINTS)
def test_non_sellers_get_403(api: APIClient, method: str, url: str, role: UserRole) -> None:
    api.credentials(HTTP_X_USER_ID=str(uuid4()), HTTP_X_USER_ROLE=role.value)

    response = getattr(api, method)(url)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_seller_without_shop_gets_seller_not_found(api: APIClient) -> None:
    user_id = str(uuid4())
    api.credentials(
        HTTP_X_USER_ID=user_id, HTTP_X_USER_ROLE=UserRole.SELLER.value, HTTP_X_SELLER_ID=user_id
    )

    response = api.get(PRODUCTS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SELLER_NOT_FOUND"


def test_seller_is_found_by_user_id_without_seller_header(api: APIClient, seller: Seller) -> None:
    api.credentials(HTTP_X_USER_ID=str(seller.user_id), HTTP_X_USER_ROLE=UserRole.SELLER.value)

    assert api.get(PRODUCTS).status_code == 200


# --- products -------------------------------------------------------------------------


def test_create_product(
    seller_api: APIClient, seller: Seller, categories: dict[str, Category]
) -> None:
    response = seller_api.post(
        PRODUCTS,
        {"title": "Ноутбук Lenovo", "category_id": str(categories["laptops"].id)},
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Ноутбук Lenovo"
    assert body["slug"] == "noutbuk-lenovo"
    assert body["status"] == ProductStatus.DRAFT.value
    assert body["category"]["slug"] == "laptops"
    assert body["variants"] == []
    assert body["images"] == []
    assert body["variants_count"] == 0
    assert Product.objects.get(id=body["id"]).seller_id == seller.id


def test_same_title_twice_gets_suffixed_slug(
    seller_api: APIClient, categories: dict[str, Category]
) -> None:
    payload = {"title": "Qovun", "category_id": str(categories["clothes"].id)}

    first = seller_api.post(PRODUCTS, payload, format="json").json()
    second = seller_api.post(PRODUCTS, payload, format="json").json()

    assert (first["slug"], second["slug"]) == ("qovun", "qovun-2")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"category_id": "CATEGORY"}, "title"),
        ({"title": "X"}, "category_id"),
        ({"title": "X", "category_id": str(uuid4())}, "category_id"),
        ({"title": "X", "category_id": "INACTIVE"}, "category_id"),
        ({"title": "X", "category_id": "CATEGORY", "status": "archived"}, "status"),
        ({"title": "X", "category_id": "CATEGORY", "status": "bogus"}, "status"),
    ],
)
def test_create_product_validation(
    seller_api: APIClient, categories: dict[str, Category], payload: dict[str, str], field: str
) -> None:
    replacements = {
        "CATEGORY": str(categories["phones"].id),
        "INACTIVE": str(categories["hidden"].id),
    }
    payload = {key: replacements.get(value, value) for key, value in payload.items()}

    response = seller_api.post(PRODUCTS, payload, format="json")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in error["details"]


def test_list_own_products_with_filters(
    seller_api: APIClient, seller: Seller, other_seller: Seller
) -> None:
    phone = make_product(seller=seller, title="Smart phone", status=ProductStatus.ACTIVE.value)
    draft = make_product(seller=seller, title="Draft case", status=ProductStatus.DRAFT.value)
    make_variant(product=draft, sku="CASE-001")
    make_product(seller=other_seller, title="Smart watch")

    def ids(query: str = "") -> list[str]:
        body = seller_api.get(f"{PRODUCTS}{query}").json()
        return sorted(item["id"] for item in body["items"])

    assert ids() == sorted([str(phone.id), str(draft.id)])
    assert ids("?status=draft") == [str(draft.id)]
    assert ids("?q=smart") == [str(phone.id)]
    assert ids("?q=case-001") == [str(draft.id)]
    assert ids("?q=%20") == sorted([str(phone.id), str(draft.id)])
    invalid = seller_api.get(f"{PRODUCTS}?status=bogus")
    assert invalid.status_code == 400


def test_list_item_shape(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)
    make_variant(product=product, price_tiyin=300, stock=1)
    make_variant(product=product, price_tiyin=100, stock=0)

    item = seller_api.get(PRODUCTS).json()["items"][0]

    assert item["variants_count"] == 2
    assert item["min_price_tiyin"] == 100
    assert item["max_price_tiyin"] == 300
    assert item["in_stock"] is True
    assert item["status"] == ProductStatus.ACTIVE.value


def test_retrieve_own_product_with_inactive_variants(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller, status=ProductStatus.DRAFT.value)
    make_variant(product=product, is_active=False, stock=4, reserved=1)

    response = seller_api.get(product_url(product.id))

    assert response.status_code == 200
    variant = response.json()["variants"][0]
    assert variant["is_active"] is False
    assert (variant["stock"], variant["reserved"], variant["available"]) == (4, 1, 3)


def test_update_product(
    seller_api: APIClient, seller: Seller, categories: dict[str, Category]
) -> None:
    product = make_product(seller=seller, status=ProductStatus.DRAFT.value, slug="old-slug")

    response = seller_api.patch(
        product_url(product.id),
        {
            "title": "New title",
            "description": "",
            "status": "active",
            "category_id": str(categories["laptops"].id),
        },
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New title"
    assert body["description"] == ""
    assert body["status"] == "active"
    assert body["category"]["slug"] == "laptops"
    assert body["slug"] == "old-slug"  # links stay valid after a rename


def test_delete_archives(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)

    response = seller_api.delete(product_url(product.id))

    assert response.status_code == 204
    product.refresh_from_db()
    assert product.status == ProductStatus.ARCHIVED.value
    assert seller_api.get(product_url(product.id)).json()["status"] == "archived"


def test_put_is_not_allowed(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)

    assert seller_api.put(product_url(product.id), {}, format="json").status_code == 405


# --- isolation --------------------------------------------------------------------------


def test_other_sellers_product_is_not_found(seller_api: APIClient, other_seller: Seller) -> None:
    foreign = make_product(seller=other_seller, title="Theirs")
    foreign_variant = make_variant(product=foreign, stock=5)
    url = product_url(foreign.id)

    responses = [
        seller_api.get(url),
        seller_api.patch(url, {"title": "Mine now"}, format="json"),
        seller_api.delete(url),
        seller_api.post(
            f"{url}variants/", {"sku": "X-1", "price_tiyin": 1, "stock": 1}, format="json"
        ),
        seller_api.post(f"{url}images/", {"key": f"products/{foreign.id}/a.jpg"}, format="json"),
        seller_api.patch(variant_url(foreign_variant.id), {"price_tiyin": 1}, format="json"),
        seller_api.patch(f"{variant_url(foreign_variant.id)}stock/", {"stock": 0}, format="json"),
    ]

    assert [r.status_code for r in responses] == [404] * len(responses)
    assert all(r.json()["error"]["code"] == "NOT_FOUND" for r in responses)
    foreign.refresh_from_db()
    foreign_variant.refresh_from_db()
    assert foreign.title == "Theirs"
    assert foreign.status == ProductStatus.ACTIVE.value
    assert foreign_variant.stock == 5
    assert foreign_variant.price_tiyin != 1
    assert not ProductVariant.objects.filter(sku="X-1").exists()
    assert Outbox.objects.count() == 0
    listed = seller_api.get(PRODUCTS).json()
    assert listed["total"] == 0


def test_unknown_product_is_not_found(seller_api: APIClient) -> None:
    assert seller_api.get(product_url(uuid4())).status_code == 404


# --- variants ---------------------------------------------------------------------------


def test_create_variant(
    seller_api: APIClient, seller: Seller, attributes: dict[str, AttributeValue]
) -> None:
    product = make_product(seller=seller)

    response = seller_api.post(
        f"{product_url(product.id)}variants/",
        {
            "sku": "S25-RED-128",
            "price_tiyin": 1_299_900_00,
            "stock": 7,
            "attribute_value_ids": [str(attributes["red"].id), str(attributes["128"].id)],
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "S25-RED-128"
    assert body["price_tiyin"] == 1_299_900_00
    assert (body["stock"], body["reserved"], body["available"]) == (7, 0, 7)
    assert body["is_active"] is True
    assert sorted(a["code"] for a in body["attributes"]) == ["color", "memory"]


def test_create_variant_without_attributes(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)

    response = seller_api.post(
        f"{product_url(product.id)}variants/",
        {"sku": "PLAIN", "price_tiyin": 100, "stock": 0},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["attributes"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"sku": "A", "price_tiyin": 0, "stock": 1},
        {"sku": "A", "price_tiyin": -5, "stock": 1},
        {"sku": "A", "price_tiyin": 10, "stock": -1},
        {"sku": "bad sku!", "price_tiyin": 10, "stock": 1},
        {"sku": "A", "price_tiyin": "12.5", "stock": 1},
    ],
)
def test_create_variant_validation(
    seller_api: APIClient, seller: Seller, payload: dict[str, Any]
) -> None:
    product = make_product(seller=seller)

    response = seller_api.post(f"{product_url(product.id)}variants/", payload, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_variant_rejects_unknown_and_repeated_attributes(
    seller_api: APIClient, seller: Seller, attributes: dict[str, AttributeValue]
) -> None:
    product = make_product(seller=seller)
    url = f"{product_url(product.id)}variants/"

    unknown = seller_api.post(
        url,
        {"sku": "A1", "price_tiyin": 10, "stock": 1, "attribute_value_ids": [str(uuid4())]},
        format="json",
    )
    repeated = seller_api.post(
        url,
        {
            "sku": "A2",
            "price_tiyin": 10,
            "stock": 1,
            "attribute_value_ids": [str(attributes["red"].id), str(attributes["black"].id)],
        },
        format="json",
    )

    assert unknown.status_code == 400
    assert "attribute_value_ids" in unknown.json()["error"]["details"]
    assert repeated.status_code == 400
    assert "color" in repeated.json()["error"]["details"]["attribute_value_ids"][0]


def test_duplicate_sku_and_combination_conflict(
    seller_api: APIClient, seller: Seller, attributes: dict[str, AttributeValue]
) -> None:
    product = make_product(seller=seller)
    url = f"{product_url(product.id)}variants/"
    red = [str(attributes["red"].id)]
    make_variant(sku="TAKEN")
    assert (
        seller_api.post(
            url,
            {"sku": "RED", "price_tiyin": 10, "stock": 1, "attribute_value_ids": red},
            format="json",
        ).status_code
        == 201
    )

    same_sku = seller_api.post(url, {"sku": "TAKEN", "price_tiyin": 10, "stock": 1}, format="json")
    same_values = seller_api.post(
        url,
        {"sku": "RED-2", "price_tiyin": 10, "stock": 1, "attribute_value_ids": red},
        format="json",
    )

    assert same_sku.status_code == 409
    assert same_sku.json()["error"]["code"] == "SKU_TAKEN"
    assert same_values.status_code == 409
    assert same_values.json()["error"]["code"] == "VARIANT_EXISTS"


def test_update_variant(seller_api: APIClient, seller: Seller) -> None:
    variant = make_variant(product=make_product(seller=seller), sku="OLD", price_tiyin=10)

    response = seller_api.patch(
        variant_url(variant.id),
        {"sku": "NEW", "price_tiyin": 25, "is_active": False},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["sku"], body["price_tiyin"], body["is_active"]) == ("NEW", 25, False)


def test_update_variant_to_taken_sku_conflicts(seller_api: APIClient, seller: Seller) -> None:
    variant = make_variant(product=make_product(seller=seller))
    make_variant(sku="TAKEN")

    response = seller_api.patch(variant_url(variant.id), {"sku": "TAKEN"}, format="json")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "SKU_TAKEN",
        "message": "This SKU is already used.",
        "details": {"sku": "TAKEN"},
    }


def test_update_variant_rejects_non_positive_price(seller_api: APIClient, seller: Seller) -> None:
    variant = make_variant(product=make_product(seller=seller))

    response = seller_api.patch(variant_url(variant.id), {"price_tiyin": 0}, format="json")

    assert response.status_code == 400


def test_set_stock(seller_api: APIClient, seller: Seller) -> None:
    variant = make_variant(product=make_product(seller=seller), stock=5, reserved=2)

    response = seller_api.patch(f"{variant_url(variant.id)}stock/", {"stock": 2}, format="json")

    assert response.status_code == 200
    assert (response.json()["stock"], response.json()["available"]) == (2, 0)


def test_stock_below_reserved_conflicts(seller_api: APIClient, seller: Seller) -> None:
    variant = make_variant(product=make_product(seller=seller), stock=5, reserved=3)

    response = seller_api.patch(f"{variant_url(variant.id)}stock/", {"stock": 2}, format="json")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "STOCK_BELOW_RESERVED"
    assert error["details"] == {"reserved": 3}
    variant.refresh_from_db()
    assert variant.stock == 5


def test_negative_stock_is_a_validation_error(seller_api: APIClient, seller: Seller) -> None:
    variant = make_variant(product=make_product(seller=seller))

    response = seller_api.patch(f"{variant_url(variant.id)}stock/", {"stock": -1}, format="json")

    assert response.status_code == 400


def test_unknown_variant_is_not_found(seller_api: APIClient) -> None:
    assert seller_api.patch(variant_url(uuid4()), {}, format="json").status_code == 404


# --- attributes -------------------------------------------------------------------------


def test_attributes_with_values(
    seller_api: APIClient, attributes: dict[str, AttributeValue]
) -> None:
    response = seller_api.get("/api/catalog/attributes/")

    assert response.status_code == 200
    body = response.json()
    assert [a["code"] for a in body] == ["color", "memory"]
    assert [v["value"] for v in body[0]["values"]] == ["black", "red"]
    assert body[0]["values"][0]["id"] == str(attributes["black"].id)
