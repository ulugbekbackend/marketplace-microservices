"""Search tests run against the real Elasticsearch of the dev stack, each under its own
throw-away alias, with an in-memory Redis stand-in and the catalog behind MockTransport.

Tests that need Elasticsearch are skipped when it is not reachable.
"""

import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from app.core.config import Settings
from app.main import create_app, wire
from app.services.index import ProductIndex, epoch_millis
from decouple import config
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from contracts.events import ProductAttribute, ProductUpdated

ES_URL: str = config("SEARCH_TEST_ELASTICSEARCH_URL", default="http://127.0.0.1:59200")
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


@cache
def es_available() -> bool:
    for _ in range(3):  # Docker Desktop can be slow to accept the first connection
        try:
            return httpx.get(ES_URL, timeout=5.0).status_code == 200
        except httpx.HTTPError:
            continue
    return False


def closed_port_url() -> str:
    """A local URL nothing listens on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


class FakeRedis:
    """The few commands the service uses: SET NX EX, GET, DELETE."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, *keys: str) -> int:
        return sum(self.data.pop(key, None) is not None for key in keys)

    async def aclose(self) -> None:
        return None


@dataclass
class FakeCatalog:
    """Search documents the fake catalog serves, page by page."""

    documents: list[dict[str, Any]] = field(default_factory=list)
    requests: list[dict[str, str]] = field(default_factory=list)
    status: int = 200
    on_page: Callable[[int], Awaitable[None]] | None = None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/catalog/search-documents/"
        params = dict(request.url.params)
        self.requests.append(params)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "down"})
        page, page_size = int(params["page"]), int(params["page_size"])
        if self.on_page is not None:
            await self.on_page(page)
        start = (page - 1) * page_size
        return httpx.Response(
            200,
            json={
                "items": self.documents[start : start + page_size],
                "total": len(self.documents),
                "page": page,
                "page_size": page_size,
            },
        )


def make_product(
    *,
    title: str = "Telefon Samsung Galaxy",
    description: str = "",
    product_id: UUID | None = None,
    seller_id: UUID | None = None,
    shop_name: str = "Tech Shop",
    categories: Iterable[tuple[UUID, str]] = (),
    min_price: int = 100_000_00,
    max_price: int | None = None,
    in_stock: bool = True,
    attributes: Iterable[tuple[str, str]] = (),
    rating: float = 4.0,
    created_at: datetime = BASE_TIME,
    updated_at: datetime | None = None,
    image_url: str | None = "https://img.example/p.jpg",
) -> ProductUpdated:
    product_id = product_id or uuid4()
    chain = list(categories)
    return ProductUpdated(
        product_id=product_id,
        seller_id=seller_id or uuid4(),
        shop_name=shop_name,
        title=title,
        slug=f"p-{product_id.hex[:8]}",
        description=description,
        category_ids=[category_id for category_id, _ in chain],
        category_path=[name for _, name in chain],
        min_price_tiyin=min_price,
        max_price_tiyin=max_price if max_price is not None else min_price,
        in_stock=in_stock,
        attributes=[ProductAttribute(code=code, value=value) for code, value in attributes],
        rating=rating,
        image_url=image_url,
        created_at=created_at,
        updated_at=updated_at or created_at + timedelta(minutes=1),
    )


def make_settings(alias: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "elasticsearch_url": ES_URL,
        "elasticsearch_timeout": 5.0,
        "index_alias": alias,
        "index_shards": 1,
        "index_replicas": 0,
        "redis_url": "redis://unused",
        "rabbitmq_url": "",
        "consumer_enabled": False,
        "catalog_url": "http://catalog",
        "catalog_timeout": 2.0,
        "reindex_page_size": 200,
        "reindex_lock_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)


async def drop_indices(es: AsyncElasticsearch, alias: str) -> None:
    leftovers = await es.indices.get(index=f"{alias}_v*")
    for name in leftovers.body:
        await es.indices.delete(index=name, ignore_unavailable=True)


def new_alias() -> str:
    return f"test_{uuid4().hex[:12]}_products"


def build_app(
    es: AsyncElasticsearch, alias: str, redis: FakeRedis, catalog: FakeCatalog
) -> tuple[FastAPI, httpx.AsyncClient]:
    settings = make_settings(alias)
    application = create_app(with_lifespan=False)
    http = httpx.AsyncClient(
        base_url=settings.catalog_url, transport=httpx.MockTransport(catalog.handle)
    )
    wire(application, settings, es, redis, http)  # type: ignore[arg-type]
    return application, http


@pytest.fixture
def alias() -> str:
    return new_alias()


@pytest.fixture
async def es(alias: str) -> AsyncIterator[AsyncElasticsearch]:
    if not es_available():
        pytest.skip(f"Elasticsearch is not reachable at {ES_URL}")
    client = AsyncElasticsearch(ES_URL, request_timeout=10)
    yield client
    await drop_indices(client, alias)
    await client.close()


@pytest.fixture
def index(es: AsyncElasticsearch, alias: str) -> ProductIndex:
    return ProductIndex(es, alias=alias)


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog()


@pytest.fixture
async def app(
    es: AsyncElasticsearch, alias: str, redis: FakeRedis, catalog: FakeCatalog
) -> AsyncIterator[FastAPI]:
    application, http = build_app(es, alias, redis, catalog)
    yield application
    await http.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def seed(index: ProductIndex, products: Iterable[ProductUpdated]) -> None:
    await index.ensure()
    for product in products:
        await index.upsert(product, version=epoch_millis(product.updated_at))
    await index.refresh()
