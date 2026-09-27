"""Merge after login, favorites and the internal API used by the order service."""

from uuid import UUID, uuid4

from app.services.store import CartOwner, CartStore
from fakeredis import FakeAsyncRedis
from httpx import AsyncClient

from tests.conftest import FakeCatalog, user_headers

ITEMS = "/api/cart/items/"
MERGE = "/api/cart/merge/"
FAVORITES = "/api/cart/favorites/"


async def _add(client: AsyncClient, variant: UUID, qty: int, user: UUID | None = None) -> None:
    headers = user_headers(user) if user else {}
    response = await client.post(
        ITEMS, json={"variant_id": str(variant), "qty": qty}, headers=headers
    )
    assert response.status_code == 200, response.text


# --- merge -------------------------------------------------------------------------------


async def test_merge_adds_guest_quantities_to_the_customer_cart(
    client: AsyncClient, catalog: FakeCatalog, redis: FakeAsyncRedis
) -> None:
    user_id = uuid4()
    shared, guest_only, user_only = (catalog.add(available=200) for _ in range(3))
    await _add(client, shared, 2)
    await _add(client, guest_only, 1)
    await _add(client, shared, 3, user_id)
    await _add(client, user_only, 4, user_id)
    guest_id = client.cookies["guest_id"]

    response = await client.post(MERGE, headers=user_headers(user_id))

    assert response.status_code == 200
    items = {item["variant_id"]: item["qty"] for item in response.json()["groups"][0]["items"]}
    assert items == {str(shared): 5, str(guest_only): 1, str(user_only): 4}
    assert await redis.exists(f"cart:guest:{guest_id}", f"cart:guest:{guest_id}:prices") == 0


async def test_merge_caps_quantities_at_99(client: AsyncClient, catalog: FakeCatalog) -> None:
    user_id = uuid4()
    variant = catalog.add(available=500)
    await _add(client, variant, 60)
    await _add(client, variant, 70, user_id)

    response = await client.post(MERGE, headers=user_headers(user_id))

    assert response.json()["groups"][0]["items"][0]["qty"] == 99


async def test_merge_clears_the_guest_cookie(client: AsyncClient, catalog: FakeCatalog) -> None:
    await _add(client, catalog.add(), 1)

    response = await client.post(MERGE, headers=user_headers(uuid4()))

    cookie = response.headers["set-cookie"]
    assert cookie.startswith('guest_id=""') or "Max-Age=0" in cookie


async def test_merge_without_a_guest_cart_returns_the_customer_cart(
    client: AsyncClient, catalog: FakeCatalog
) -> None:
    user_id = uuid4()
    await _add(client, catalog.add(), 2, user_id)

    response = await client.post(MERGE, headers=user_headers(user_id))

    assert response.status_code == 200
    assert response.json()["items_count"] == 2


async def test_merge_twice_does_not_double_quantities(
    client: AsyncClient, catalog: FakeCatalog
) -> None:
    user_id = uuid4()
    variant = catalog.add()
    await _add(client, variant, 2)
    guest_id = client.cookies["guest_id"]

    await client.post(MERGE, headers=user_headers(user_id))
    client.cookies.set("guest_id", guest_id, path="/api/cart")  # a retried request
    response = await client.post(MERGE, headers=user_headers(user_id))

    assert response.json()["items_count"] == 2


async def test_merge_requires_login(client: AsyncClient) -> None:
    response = await client.post(MERGE)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_merge_keeps_the_price_the_customer_already_saw(redis: FakeAsyncRedis) -> None:
    store = CartStore(redis, ttl_seconds=100, max_qty=99)
    guest, user = CartOwner.guest(uuid4()), CartOwner.user(uuid4())
    both, guest_only = uuid4(), uuid4()
    await store.set_line(guest, both, 1, price=900)
    await store.set_line(guest, guest_only, 1, price=500)
    await store.set_line(user, both, 1, price=1_000)

    await store.merge(guest, user)

    lines = {line.variant_id: line for line in await store.lines(user)}
    assert lines[both].seen_price_tiyin == 1_000
    assert lines[both].qty == 2
    assert lines[guest_only].seen_price_tiyin == 500
    assert await redis.ttl(user.items_key) > 0


# --- favorites ---------------------------------------------------------------------------


async def test_favorites_need_login(client: AsyncClient) -> None:
    response = await client.get(FAVORITES)

    assert response.status_code == 401


async def test_add_list_and_remove_favorites(client: AsyncClient) -> None:
    headers = user_headers(uuid4())
    first, second = uuid4(), uuid4()

    await client.post(FAVORITES, json={"product_id": str(first)}, headers=headers)
    added = await client.post(FAVORITES, json={"product_id": str(second)}, headers=headers)
    again = await client.post(FAVORITES, json={"product_id": str(first)}, headers=headers)
    removed = await client.delete(f"{FAVORITES}{first}/", headers=headers)
    listed = await client.get(FAVORITES, headers=headers)

    assert sorted(added.json()["items"]) == sorted([str(first), str(second)])
    assert len(again.json()["items"]) == 2
    assert removed.status_code == 204
    assert listed.json() == {"items": [str(second)]}


async def test_favorites_are_per_customer(client: AsyncClient) -> None:
    product = uuid4()
    await client.post(FAVORITES, json={"product_id": str(product)}, headers=user_headers(uuid4()))

    response = await client.get(FAVORITES, headers=user_headers(uuid4()))

    assert response.json() == {"items": []}


async def test_favorites_have_a_limit(client: AsyncClient, redis: FakeAsyncRedis) -> None:
    user_id = uuid4()
    await redis.sadd(f"fav:user:{user_id}", *(str(uuid4()) for _ in range(500)))

    response = await client.post(
        FAVORITES, json={"product_id": str(uuid4())}, headers=user_headers(user_id)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FAVORITES_FULL"


# --- internal ----------------------------------------------------------------------------


async def test_internal_cart_returns_raw_quantities(
    client: AsyncClient, catalog: FakeCatalog
) -> None:
    user_id = uuid4()
    variant = catalog.add()
    await _add(client, variant, 3, user_id)
    calls = len(catalog.requests)

    response = await client.get(f"/internal/cart/{user_id}")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id),
        "items": [{"variant_id": str(variant), "qty": 3}],
    }
    assert len(catalog.requests) == calls  # no price lookup: the order service does that


async def test_internal_clear(client: AsyncClient, catalog: FakeCatalog) -> None:
    user_id = uuid4()
    await _add(client, catalog.add(), 3, user_id)

    response = await client.delete(f"/internal/cart/{user_id}")

    assert response.status_code == 204
    assert (await client.get(f"/internal/cart/{user_id}")).json()["items"] == []


async def test_internal_routes_are_not_in_the_public_schema(client: AsyncClient) -> None:
    schema = (await client.get("/api/cart/openapi.json")).json()

    assert all(not path.startswith("/internal") for path in schema["paths"])
    assert "/api/cart/items/" in schema["paths"]
