# ruff: noqa: RUF001 - Cyrillic and apostrophe variants are the test data
"""GET /api/search/suggest: prefix suggestions in any script, at most eight."""

from uuid import UUID

import pytest
from app.services.index import ProductIndex
from app.services.search import SearchService
from elasticsearch import AsyncElasticsearch
from httpx import AsyncClient

from tests.conftest import closed_port_url, make_product, seed


async def suggest(client: AsyncClient, q: str) -> list[dict[str, str]]:
    response = await client.get("/api/search/suggest", params={"q": q})
    assert response.status_code == 200, response.text
    items: list[dict[str, str]] = response.json()["items"]
    return items


@pytest.fixture
async def products(index: ProductIndex) -> dict[str, UUID]:
    catalog = {
        "phone": make_product(title="Telefon Samsung Galaxy"),
        "tv": make_product(title="Televizor LG", rating=4.9),
        "toy": make_product(title="Oʻyinchoq mashina"),
        "bag": make_product(title="Sumka charm"),
    }
    await seed(index, catalog.values())
    return {name: product.product_id for name, product in catalog.items()}


async def test_prefix_suggestions_carry_link_fields(
    client: AsyncClient, products: dict[str, UUID]
) -> None:
    items = await suggest(client, "tel")

    assert {UUID(item["id"]) for item in items} == {products["phone"], products["tv"]}
    assert set(items[0]) == {"id", "slug", "title"}


async def test_cyrillic_prefix_suggests_latin_titles(
    client: AsyncClient, products: dict[str, UUID]
) -> None:
    items = await suggest(client, "телеф")

    assert [UUID(item["id"]) for item in items] == [products["phone"]]


@pytest.mark.parametrize("q", ["o'yin", "oʻyin", "ўйин", "oyin"])
async def test_apostrophe_and_cyrillic_prefixes(
    client: AsyncClient, products: dict[str, UUID], q: str
) -> None:
    items = await suggest(client, q)

    assert [UUID(item["id"]) for item in items] == [products["toy"]]


async def test_every_word_must_match(client: AsyncClient, products: dict[str, UUID]) -> None:
    assert [item["title"] for item in await suggest(client, "telefon gal")] == [
        "Telefon Samsung Galaxy"
    ]
    assert await suggest(client, "telefon lg") == []


@pytest.mark.parametrize("q", ["", " ", "t"])
async def test_too_short_query_suggests_nothing(
    client: AsyncClient, products: dict[str, UUID], q: str
) -> None:
    assert await suggest(client, q) == []


async def test_at_most_eight_unique_titles(client: AsyncClient, index: ProductIndex) -> None:
    await seed(
        index,
        [make_product(title=f"Kitob {n}") for n in range(12)]
        + [make_product(title="Kitob 0") for _ in range(3)],
    )

    items = await suggest(client, "kitob")

    titles = [item["title"] for item in items]
    assert len(titles) == 8
    assert len(set(titles)) == 8


async def test_missing_index_suggests_nothing(client: AsyncClient) -> None:
    assert await suggest(client, "telefon") == []


async def test_query_is_limited(client: AsyncClient) -> None:
    response = await client.get("/api/search/suggest", params={"q": "x" * 101})

    assert response.status_code == 400


async def test_elasticsearch_down_is_503() -> None:
    es = AsyncElasticsearch(closed_port_url(), request_timeout=1, max_retries=0)
    service = SearchService(es, alias="products")
    try:
        with pytest.raises(Exception) as caught:
            await service.suggest("telefon")
    finally:
        await es.close()

    assert getattr(caught.value, "code", None) == "SEARCH_UNAVAILABLE"
    assert getattr(caught.value, "status", None) == 503
