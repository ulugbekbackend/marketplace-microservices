"""Category words in text search, and deleted products (tombstones) staying hidden."""

from typing import Any
from uuid import uuid4

from app.services.index import ProductIndex
from httpx import AsyncClient

from tests.conftest import make_product, seed

PHONES = [(uuid4(), "Elektronika"), (uuid4(), "Telefonlar"), (uuid4(), "Smartfonlar")]
TOYS = [(uuid4(), "O'yinchoqlar")]


async def search(client: AsyncClient, q: str) -> set[str]:
    response = await client.get("/api/search", params={"q": q})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return {item["title"] for item in body["items"]}


async def test_a_singular_word_finds_products_of_a_plural_category(
    client: AsyncClient, index: ProductIndex
) -> None:
    await seed(
        index,
        [
            make_product(title="Samsung Galaxy S25", categories=PHONES),
            make_product(title="Yumshoq ayiq", categories=TOYS),
        ],
    )

    assert await search(client, "telefon") == {"Samsung Galaxy S25"}
    assert await search(client, "смартфон") == {"Samsung Galaxy S25"}
    assert await search(client, "samsung telefon") == {"Samsung Galaxy S25"}
    assert await search(client, "telefon ayiq") == set()


async def test_deleted_products_are_left_out_of_search_and_suggestions(
    client: AsyncClient, index: ProductIndex
) -> None:
    kept = make_product(title="Galaxy Buds", categories=PHONES)
    gone = make_product(title="Galaxy Watch", categories=PHONES)
    await seed(index, [kept, gone])
    await index.delete(gone.product_id, version=10**13)
    await index.refresh()

    assert await search(client, "galaxy") == {"Galaxy Buds"}
    assert await search(client, "") == {"Galaxy Buds"}
    response = await client.get("/api/search/suggest", params={"q": "gala"})
    assert [item["title"] for item in response.json()["items"]] == ["Galaxy Buds"]
    facets = (await client.get("/api/search")).json()["facets"]
    assert sum(category["count"] for category in facets["categories"]) == 3  # 1 product x 3
