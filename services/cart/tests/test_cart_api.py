"""Cart endpoints: guest cookie, validation, stock and price flags, grouping, TTL."""

from uuid import uuid4

from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import SELLER_B, FakeCatalog, user_headers

CART = "/api/cart/"
ITEMS = "/api/cart/items/"


async def test_first_guest_request_sets_an_http_only_cookie(client: AsyncClient) -> None:
    response = await client.get(CART)

    assert response.status_code == 200
    assert response.json() == {
        "groups": [],
        "total_tiyin": 0,
        "items_count": 0,
        "has_unavailable": False,
        "has_price_changes": False,
        "removed": [],
    }
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("guest_id=")
    assert "HttpOnly" in cookie
    assert "Path=/api/cart" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=2592000" in cookie


async def test_guest_keeps_the_same_cart_across_requests(
    client: AsyncClient, catalog: FakeCatalog
) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 2})

    response = await client.get(CART)

    assert "set-cookie" not in response.headers
    assert response.json()["items_count"] == 2


async def test_signed_in_customer_gets_no_guest_cookie(client: AsyncClient) -> None:
    response = await client.get(CART, headers=user_headers(uuid4()))

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


async def test_add_item_returns_the_cart_with_current_catalog_data(
    client: AsyncClient, catalog: FakeCatalog
) -> None:
    variant = catalog.add(price=25_000, available=7)

    response = await client.post(ITEMS, json={"variant_id": str(variant), "qty": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["total_tiyin"] == 75_000
    assert body["items_count"] == 3
    [group] = body["groups"]
    assert group["shop_name"] == "Shop A"
    assert group["subtotal_tiyin"] == 75_000
    [item] = group["items"]
    assert item["variant_id"] == str(variant)
    assert item["qty"] == 3
    assert item["price_tiyin"] == 25_000
    assert item["line_total_tiyin"] == 75_000
    assert item["available_qty"] == 7
    assert item["available"] is True
    assert item["price_changed"] is False
    assert item["previous_price_tiyin"] is None
    assert item["attributes"] == [{"code": "size", "name": "Size", "value": "M"}]


async def test_adding_again_increases_the_quantity(
    client: AsyncClient, catalog: FakeCatalog
) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 2})

    response = await client.post(ITEMS, json={"variant_id": str(variant), "qty": 3})

    assert response.json()["groups"][0]["items"][0]["qty"] == 5


async def test_quantity_is_capped_at_99(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add(available=500)
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 90})

    response = await client.post(ITEMS, json={"variant_id": str(variant), "qty": 20})

    assert response.json()["groups"][0]["items"][0]["qty"] == 99


async def test_qty_defaults_to_one(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add()

    response = await client.post(ITEMS, json={"variant_id": str(variant)})

    assert response.json()["items_count"] == 1


async def test_qty_outside_1_99_is_rejected(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add()

    for qty in (0, 100, -1):
        response = await client.post(ITEMS, json={"variant_id": str(variant), "qty": qty})
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert "qty" in error["details"]


async def test_bad_variant_id_is_rejected(client: AsyncClient) -> None:
    response = await client.post(ITEMS, json={"variant_id": "nope", "qty": 1})

    assert response.status_code == 400
    assert "variant_id" in response.json()["error"]["details"]


async def test_unknown_variant_is_404(client: AsyncClient) -> None:
    response = await client.post(ITEMS, json={"variant_id": str(uuid4()), "qty": 1})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VARIANT_NOT_FOUND"


async def test_inactive_variant_cannot_be_added(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add(is_active=False)

    response = await client.post(ITEMS, json={"variant_id": str(variant), "qty": 1})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VARIANT_INACTIVE"


async def test_cannot_add_more_than_the_stock(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add(available=2)
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 2})

    response = await client.post(ITEMS, json={"variant_id": str(variant), "qty": 1})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "OUT_OF_STOCK"
    assert error["details"] == {"variant_id": str(variant), "available": 2}
    assert (await client.get(CART)).json()["items_count"] == 2


async def test_cart_has_a_limit_of_different_items(
    app: FastAPI, catalog: FakeCatalog, client: AsyncClient
) -> None:
    app.state.cart_service._max_lines = 2
    first, second, third = catalog.add(), catalog.add(), catalog.add()
    await client.post(ITEMS, json={"variant_id": str(first)})
    await client.post(ITEMS, json={"variant_id": str(second)})

    rejected = await client.post(ITEMS, json={"variant_id": str(third)})
    more_of_existing = await client.post(ITEMS, json={"variant_id": str(first)})

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "CART_FULL"
    assert more_of_existing.status_code == 200


async def test_patch_sets_the_quantity(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 5})

    response = await client.patch(f"{ITEMS}{variant}/", json={"qty": 2})

    assert response.status_code == 200
    assert response.json()["items_count"] == 2


async def test_patch_to_zero_removes_the_item(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 5})

    response = await client.patch(f"{ITEMS}{variant}/", json={"qty": 0})

    assert response.status_code == 200
    assert response.json()["groups"] == []


async def test_patch_above_stock_is_rejected(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add(available=3)
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 1})

    response = await client.patch(f"{ITEMS}{variant}/", json={"qty": 4})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OUT_OF_STOCK"


async def test_patch_or_delete_of_an_item_not_in_the_cart_is_404(client: AsyncClient) -> None:
    missing = uuid4()

    patched = await client.patch(f"{ITEMS}{missing}/", json={"qty": 1})
    deleted = await client.delete(f"{ITEMS}{missing}/")

    assert patched.status_code == 404
    assert patched.json()["error"]["code"] == "NOT_IN_CART"
    assert deleted.status_code == 404


async def test_delete_item(client: AsyncClient, catalog: FakeCatalog) -> None:
    keep, drop = catalog.add(), catalog.add()
    await client.post(ITEMS, json={"variant_id": str(keep)})
    await client.post(ITEMS, json={"variant_id": str(drop)})

    response = await client.delete(f"{ITEMS}{drop}/")

    items = response.json()["groups"][0]["items"]
    assert [item["variant_id"] for item in items] == [str(keep)]


async def test_clear_cart(client: AsyncClient, catalog: FakeCatalog) -> None:
    await client.post(ITEMS, json={"variant_id": str(catalog.add())})

    response = await client.delete(CART)

    assert response.status_code == 204
    assert (await client.get(CART)).json()["groups"] == []


async def test_items_are_grouped_by_seller(client: AsyncClient, catalog: FakeCatalog) -> None:
    a1 = catalog.add(price=1_000)
    b1 = catalog.add(price=5_000, seller_id=SELLER_B, shop_name="Shop B")
    a2 = catalog.add(price=2_000)
    for variant in (a1, b1, a2):
        await client.post(ITEMS, json={"variant_id": str(variant), "qty": 2})

    body = (await client.get(CART)).json()

    groups = {group["shop_name"]: group for group in body["groups"]}
    assert set(groups) == {"Shop A", "Shop B"}
    assert len(groups["Shop A"]["items"]) == 2
    assert groups["Shop A"]["subtotal_tiyin"] == 6_000
    assert groups["Shop B"]["subtotal_tiyin"] == 10_000
    assert body["total_tiyin"] == 16_000
    assert body["items_count"] == 6


async def test_price_change_is_flagged(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    variant = catalog.add(price=10_000)
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 1})
    catalog.variants[variant]["price_tiyin"] = 12_000
    await redis.delete(f"cart:catalog:variant:{variant}")  # the 30 s cache ran out

    body = (await client.get(CART)).json()

    item = body["groups"][0]["items"][0]
    assert item["price_tiyin"] == 12_000
    assert item["price_changed"] is True
    assert item["previous_price_tiyin"] == 10_000
    assert body["has_price_changes"] is True
    assert body["total_tiyin"] == 12_000


async def test_updating_the_item_accepts_the_new_price(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    variant = catalog.add(price=10_000)
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 1})
    catalog.variants[variant]["price_tiyin"] = 9_000
    await redis.delete(f"cart:catalog:variant:{variant}")

    body = (await client.patch(f"{ITEMS}{variant}/", json={"qty": 2})).json()

    assert body["groups"][0]["items"][0]["price_changed"] is False
    assert body["has_price_changes"] is False


async def test_stock_drop_marks_the_item_unavailable(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    fine = catalog.add(price=1_000)
    short = catalog.add(price=3_000, available=5)
    await client.post(ITEMS, json={"variant_id": str(fine)})
    await client.post(ITEMS, json={"variant_id": str(short), "qty": 4})
    catalog.variants[short]["available"] = 2
    await redis.delete(f"cart:catalog:variant:{short}")

    body = (await client.get(CART)).json()

    items = {item["variant_id"]: item for item in body["groups"][0]["items"]}
    assert items[str(short)]["available"] is False
    assert items[str(short)]["available_qty"] == 2
    assert items[str(fine)]["available"] is True
    assert body["has_unavailable"] is True
    assert body["total_tiyin"] == 1_000  # only what can be bought


async def test_deactivated_variant_stays_but_is_unavailable(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant)})
    catalog.variants[variant]["is_active"] = False
    await redis.delete(f"cart:catalog:variant:{variant}")

    body = (await client.get(CART)).json()

    assert body["groups"][0]["items"][0]["available"] is False
    assert body["total_tiyin"] == 0


async def test_deleted_variant_is_dropped_and_reported(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    keep, gone = catalog.add(), catalog.add()
    await client.post(ITEMS, json={"variant_id": str(keep)})
    await client.post(ITEMS, json={"variant_id": str(gone)})
    del catalog.variants[gone]
    await redis.delete(f"cart:catalog:variant:{gone}")

    first = (await client.get(CART)).json()
    second = (await client.get(CART)).json()

    assert first["removed"] == [str(gone)]
    assert [item["variant_id"] for item in first["groups"][0]["items"]] == [str(keep)]
    assert second["removed"] == []


async def test_catalog_lookups_are_cached(client: AsyncClient, catalog: FakeCatalog) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant)})
    calls = len(catalog.requests)

    await client.get(CART)
    await client.get(CART)

    assert len(catalog.requests) == calls


async def test_catalog_cache_expires_after_30_seconds(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant)})

    ttl = await redis.ttl(f"cart:catalog:variant:{variant}")

    assert 0 < ttl <= 30


async def test_catalog_outage_is_503(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant)})
    catalog.down = True
    await redis.delete(f"cart:catalog:variant:{variant}")

    response = await client.get(CART)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CATALOG_UNAVAILABLE"


async def test_empty_cart_does_not_call_the_catalog(
    client: AsyncClient, catalog: FakeCatalog
) -> None:
    await client.get(CART)

    assert catalog.requests == []


async def test_every_write_refreshes_the_30_day_ttl(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    user_id = uuid4()
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant)}, headers=user_headers(user_id))
    await redis.expire(f"cart:user:{user_id}", 60)

    await client.patch(f"{ITEMS}{variant}/", json={"qty": 2}, headers=user_headers(user_id))

    for key in (f"cart:user:{user_id}", f"cart:user:{user_id}:prices"):
        ttl = await redis.ttl(key)
        assert 30 * 24 * 3600 - 5 < ttl <= 30 * 24 * 3600


async def test_guest_and_customer_carts_are_separate(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    user_id = uuid4()
    variant = catalog.add()
    await client.post(ITEMS, json={"variant_id": str(variant), "qty": 1})
    await client.post(
        ITEMS, json={"variant_id": str(variant), "qty": 4}, headers=user_headers(user_id)
    )

    assert await redis.hget(f"cart:user:{user_id}", str(variant)) == "4"
    guest_id = client.cookies["guest_id"]
    assert await redis.hget(f"cart:guest:{guest_id}", str(variant)) == "1"


async def test_malformed_identity_headers_are_401(client: AsyncClient) -> None:
    response = await client.get(CART, headers={"X-User-Id": "x", "X-User-Role": "customer"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_invalid_guest_cookie_is_replaced(client: AsyncClient) -> None:
    client.cookies.set("guest_id", "not-a-uuid", path="/api/cart")

    response = await client.get(CART)

    assert response.status_code == 200
    assert response.headers["set-cookie"].startswith("guest_id=")
