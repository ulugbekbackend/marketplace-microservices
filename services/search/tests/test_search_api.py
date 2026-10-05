# ruff: noqa: RUF001 - Cyrillic and apostrophe variants are the test data
"""GET /api/search: text, transliteration, filters, sorting, paging and facets."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from app.services.index import ProductIndex
from elasticsearch import AsyncElasticsearch
from httpx import ASGITransport, AsyncClient

from tests.conftest import (
    BASE_TIME,
    ES_URL,
    FakeCatalog,
    FakeRedis,
    build_app,
    drop_indices,
    es_available,
    make_product,
    new_alias,
    seed,
)

# The catalog below is indexed once for the whole module; the tests only read it.
pytestmark = pytest.mark.asyncio(loop_scope="module")

ELEC = UUID("00000000-0000-0000-0000-0000000000e1")
PHONES = UUID("00000000-0000-0000-0000-0000000000e2")
TV = UUID("00000000-0000-0000-0000-0000000000e3")
TOYS = UUID("00000000-0000-0000-0000-0000000000f1")
SELLER_1 = UUID("00000000-0000-0000-0000-00000000005a")
SELLER_2 = UUID("00000000-0000-0000-0000-00000000005b")

P1 = UUID("00000000-0000-0000-0000-000000000001")
P2 = UUID("00000000-0000-0000-0000-000000000002")
P3 = UUID("00000000-0000-0000-0000-000000000003")
P4 = UUID("00000000-0000-0000-0000-000000000004")
P5 = UUID("00000000-0000-0000-0000-000000000005")
P6 = UUID("00000000-0000-0000-0000-000000000006")

PHONE_CHAIN = [(ELEC, "Elektronika"), (PHONES, "Telefonlar")]
TV_CHAIN = [(ELEC, "Elektronika"), (TV, "Televizorlar")]
TOY_CHAIN = [(TOYS, "O'yinchoqlar")]


def _day(n: int) -> Any:
    return BASE_TIME + timedelta(days=n)


CATALOG = [
    make_product(
        product_id=P1,
        title="Telefon Samsung Galaxy A55",
        seller_id=SELLER_1,
        shop_name="Tech Shop",
        categories=PHONE_CHAIN,
        min_price=350_000_000,
        max_price=380_000_000,
        attributes=[("color", "Black"), ("memory", "128GB")],
        rating=4.5,
        created_at=_day(1),
    ),
    make_product(
        product_id=P2,
        title="Telefon iPhone 15",
        seller_id=SELLER_2,
        shop_name="Apple Store",
        categories=PHONE_CHAIN,
        min_price=1_200_000_000,
        attributes=[("color", "Black"), ("color", "Blue"), ("color", "Black")],
        created_at=_day(2),
    ),
    make_product(
        product_id=P3,
        title="Televizor LG 55",
        seller_id=SELLER_1,
        shop_name="Tech Shop",
        categories=TV_CHAIN,
        min_price=600_000_000,
        in_stock=False,
        attributes=[("color", "Black")],
        created_at=_day(3),
    ),
    make_product(
        product_id=P4,
        title="Bolalar o'yinchoq mashina",
        seller_id=SELLER_2,
        shop_name="Apple Store",
        categories=TOY_CHAIN,
        min_price=8_000_000,
        attributes=[("color", "Red")],
        created_at=_day(4),
    ),
    make_product(
        product_id=P5,
        title="Телефон Redmi Note",
        seller_id=SELLER_1,
        shop_name="Tech Shop",
        categories=PHONE_CHAIN,
        min_price=200_000_000,
        attributes=[("color", "Blue")],
        created_at=_day(5),
    ),
    make_product(
        product_id=P6,
        title="Oʻyinchoq ayiq",
        seller_id=SELLER_1,
        shop_name="Tech Shop",
        categories=TOY_CHAIN,
        min_price=15_000_000,
        attributes=[("color", "Red")],
        created_at=_day(6),
    ),
]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def shared_es() -> AsyncIterator[AsyncElasticsearch]:
    if not es_available():
        pytest.skip(f"Elasticsearch is not reachable at {ES_URL}")
    es = AsyncElasticsearch(ES_URL, request_timeout=10)
    yield es
    await es.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def seeded(shared_es: AsyncElasticsearch) -> AsyncIterator[ProductIndex]:
    index = ProductIndex(shared_es, alias=new_alias())
    await seed(index, CATALOG)
    yield index
    await drop_indices(shared_es, index.alias)


async def _client_for(es: AsyncElasticsearch, alias: str) -> AsyncIterator[AsyncClient]:
    application, http = build_app(es, alias, FakeRedis(), FakeCatalog())
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        yield client
    await http.aclose()


@pytest_asyncio.fixture(loop_scope="module")
async def client(seeded: ProductIndex) -> AsyncIterator[AsyncClient]:
    async for http in _client_for(seeded.es, seeded.alias):
        yield http


@pytest_asyncio.fixture(loop_scope="module")
async def empty_client(shared_es: AsyncElasticsearch) -> AsyncIterator[AsyncClient]:
    async for http in _client_for(shared_es, new_alias()):
        yield http


def ids(body: dict[str, Any]) -> set[UUID]:
    return {UUID(item["id"]) for item in body["items"]}


def ordered(body: dict[str, Any]) -> list[UUID]:
    return [UUID(item["id"]) for item in body["items"]]


async def get(client: AsyncClient, params: Any) -> Any:
    response = await client.get("/api/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- text ---------------------------------------------------------------------------------


async def test_without_query_returns_everything_with_card_fields(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, {})

    assert body["total"] == 6
    assert body["page"] == 1
    assert body["page_size"] == 20
    card = next(item for item in body["items"] if item["id"] == str(P1))
    assert card == {
        "id": str(P1),
        "slug": CATALOG[0].slug,
        "title": "Telefon Samsung Galaxy A55",
        "seller_id": str(SELLER_1),
        "shop_name": "Tech Shop",
        "min_price": 350_000_000,
        "max_price": 380_000_000,
        "in_stock": True,
        "image_url": "https://img.example/p.jpg",
        "rating": 4.5,
    }


@pytest.mark.parametrize("q", ["telefon", "Telefon", "телефон", "ТЕЛЕФОН"])
async def test_latin_and_cyrillic_find_the_same_products(
    client: AsyncClient, seeded: ProductIndex, q: str
) -> None:
    body = await get(client, {"q": q})

    assert ids(body) == {P1, P2, P5}


@pytest.mark.parametrize("q", ["o'yinchoq", "oʻyinchoq", "o‘yinchoq", "o’yinchoq", "oyinchoq"])
async def test_apostrophe_variants_match(client: AsyncClient, seeded: ProductIndex, q: str) -> None:
    body = await get(client, {"q": q})

    assert ids(body) == {P4, P6}


@pytest.mark.parametrize("q", ["ўйинчоқ", "ойинчоқ", "ЎЙИНЧОҚ"])
async def test_uzbek_cyrillic_matches_latin(
    client: AsyncClient, seeded: ProductIndex, q: str
) -> None:
    body = await get(client, {"q": q})

    assert ids(body) == {P4, P6}


async def test_typo_is_tolerated(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"q": "telfon"})

    assert ids(body) == {P1, P2, P5}


async def test_unfinished_word_matches_by_prefix(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"q": "galax"})

    assert ids(body) == {P1}


async def test_words_may_come_from_different_fields(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, {"q": "redmi telefonlar"})

    assert ids(body) == {P5}


async def test_unknown_word_finds_nothing(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"q": "velosiped"})

    assert body["total"] == 0
    assert body["items"] == []


# --- filters ------------------------------------------------------------------------------


async def test_category_filter_includes_descendants(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    assert ids(await get(client, {"category": str(ELEC)})) == {P1, P2, P3, P5}
    assert ids(await get(client, {"category": str(PHONES)})) == {P1, P2, P5}


async def test_seller_filter(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"seller": str(SELLER_2)})

    assert ids(body) == {P2, P4}


async def test_price_range_filter_uses_card_price(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, {"price_min": 200_000_000, "price_max": 350_000_000})

    assert ids(body) == {P1, P5}


async def test_open_price_bounds(client: AsyncClient, seeded: ProductIndex) -> None:
    assert ids(await get(client, {"price_min": 600_000_000})) == {P2, P3}
    assert ids(await get(client, {"price_max": 15_000_000})) == {P4, P6}


async def test_in_stock_filter(client: AsyncClient, seeded: ProductIndex) -> None:
    assert ids(await get(client, {"in_stock": "false"})) == {P3}
    assert ids(await get(client, {"in_stock": "true"})) == {P1, P2, P4, P5, P6}


async def test_attribute_filter(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, [("attr[color]", "Red")])

    assert ids(body) == {P4, P6}


async def test_attribute_values_of_one_code_are_or(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, [("attr[color]", "Red"), ("attr[color]", "Blue")])

    assert ids(body) == {P2, P4, P5, P6}


async def test_attribute_codes_are_and(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, [("attr[color]", "Black"), ("attr[memory]", "128GB")])

    assert ids(body) == {P1}


async def test_attribute_filter_ignores_case(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, [("attr[color]", "red"), ("attr[size]", "  ")])

    assert ids(body) == {P4, P6}


async def test_filters_combine_with_text(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"q": "telefon", "seller": str(SELLER_1), "price_max": 300_000_000})

    assert ids(body) == {P5}


# --- sorting and paging -------------------------------------------------------------------


async def test_sort_by_price(client: AsyncClient, seeded: ProductIndex) -> None:
    ascending = ordered(await get(client, {"sort": "price_asc"}))
    descending = ordered(await get(client, {"sort": "price_desc"}))

    assert ascending == [P4, P6, P5, P1, P3, P2]
    assert descending == list(reversed(ascending))


async def test_sort_newest_first(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"sort": "newest"})

    assert ordered(body) == [P6, P5, P4, P3, P2, P1]


async def test_relevance_puts_title_phrase_first(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"q": "telefon iphone"})

    assert ordered(body)[0] == P2


async def test_paging(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"sort": "newest", "page": 2, "page_size": 2})

    assert body["total"] == 6
    assert (body["page"], body["page_size"]) == (2, 2)
    assert ordered(body) == [P4, P3]


async def test_page_past_the_end_is_empty(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"page": 5, "page_size": 10})

    assert body["total"] == 6
    assert body["items"] == []


# --- facets -------------------------------------------------------------------------------


def category_counts(body: dict[str, Any]) -> dict[str, tuple[str, int]]:
    return {item["id"]: (item["name"], item["count"]) for item in body["facets"]["categories"]}


def price_counts(body: dict[str, Any]) -> dict[str, int]:
    return {item["key"]: item["count"] for item in body["facets"]["price_ranges"]}


def attribute_counts(body: dict[str, Any]) -> dict[str, dict[str, tuple[int, bool]]]:
    return {
        facet["code"]: {
            value["value"]: (value["count"], value["selected"]) for value in facet["values"]
        }
        for facet in body["facets"]["attributes"]
    }


async def test_facets_without_filters(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {})

    assert category_counts(body) == {
        str(ELEC): ("Elektronika", 4),
        str(PHONES): ("Telefonlar", 3),
        str(TV): ("Televizorlar", 1),
        str(TOYS): ("O'yinchoqlar", 2),
    }
    assert price_counts(body) == {
        "lt_100k": 1,
        "100k_500k": 1,
        "500k_1m": 0,
        "1m_5m": 2,
        "gte_5m": 2,
    }
    bounds = {
        item["key"]: (item["from_tiyin"], item["to_tiyin"])
        for item in body["facets"]["price_ranges"]
    }
    assert bounds["lt_100k"] == (None, 10_000_000)
    assert bounds["gte_5m"] == (500_000_000, None)
    # P2 lists Black twice (two variants) and still counts once.
    assert attribute_counts(body) == {
        "color": {"Black": (3, False), "Blue": (2, False), "Red": (2, False)},
        "memory": {"128GB": (1, False)},
    }


async def test_selected_attribute_keeps_its_own_counts(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, [("attr[color]", "Red")])

    assert body["total"] == 2
    # Other colors stay selectable with their counts...
    assert attribute_counts(body)["color"] == {
        "Black": (3, False),
        "Blue": (2, False),
        "Red": (2, True),
    }
    # ...while the other facets narrow down to red products.
    assert category_counts(body) == {str(TOYS): ("O'yinchoqlar", 2)}
    assert "memory" not in attribute_counts(body)


async def test_other_attribute_codes_respect_selected_ones(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, [("attr[memory]", "128GB")])

    counts = attribute_counts(body)
    assert counts["memory"] == {"128GB": (1, True)}
    assert counts["color"] == {"Black": (1, False)}


async def test_selected_category_keeps_category_counts(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, {"category": str(PHONES)})

    assert ids(body) == {P1, P2, P5}
    assert category_counts(body)[str(TOYS)] == ("O'yinchoqlar", 2)
    assert price_counts(body) == {
        "lt_100k": 0,
        "100k_500k": 0,
        "500k_1m": 0,
        "1m_5m": 2,
        "gte_5m": 1,
    }


async def test_selected_price_keeps_price_counts(client: AsyncClient, seeded: ProductIndex) -> None:
    body = await get(client, {"price_min": 100_000_000, "price_max": 499_999_999})

    assert ids(body) == {P1, P5}
    assert price_counts(body)["lt_100k"] == 1
    assert category_counts(body) == {
        str(ELEC): ("Elektronika", 2),
        str(PHONES): ("Telefonlar", 2),
    }


async def test_non_facet_filters_narrow_every_facet(
    client: AsyncClient, seeded: ProductIndex
) -> None:
    body = await get(client, {"seller": str(SELLER_2)})

    assert category_counts(body) == {
        str(ELEC): ("Elektronika", 1),
        str(PHONES): ("Telefonlar", 1),
        str(TOYS): ("O'yinchoqlar", 1),
    }


# --- errors -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page_size": 101}, "page_size"),
        ({"page": 0}, "page"),
        ({"sort": "cheapest"}, "sort"),
        ({"price_min": -1}, "price_min"),
        ({"price_min": 10, "price_max": 5}, "price_min"),
        ({"page": 101, "page_size": 100}, "page"),
        ({"category": "phones"}, "category"),
        ({"attr[bad code]": "x"}, "attr[bad code]"),
        ({"attr[color]": "x" * 201}, "attr[color]"),
    ],
)
async def test_invalid_parameters(
    client: AsyncClient, seeded: ProductIndex, params: dict[str, Any], field: str
) -> None:
    response = await client.get("/api/search", params=params)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in error["details"]


async def test_too_many_attribute_filters(client: AsyncClient, seeded: ProductIndex) -> None:
    many_codes: Any = [(f"attr[c{n}]", "x") for n in range(21)]
    many_values: Any = [("attr[color]", f"v{n}") for n in range(51)]

    assert (await client.get("/api/search", params=many_codes)).status_code == 400
    assert (await client.get("/api/search", params=many_values)).status_code == 400


async def test_missing_index_returns_empty_result(empty_client: AsyncClient) -> None:
    body = await get(empty_client, {"q": "telefon"})

    assert body["total"] == 0
    assert body["facets"] == {"categories": [], "price_ranges": [], "attributes": []}


async def test_latency_is_measured(client: AsyncClient, seeded: ProductIndex) -> None:
    await get(client, {"q": "telefon"})

    metrics = (await client.get("/metrics")).text
    assert 'search_latency_seconds_count{endpoint="search"}' in metrics
