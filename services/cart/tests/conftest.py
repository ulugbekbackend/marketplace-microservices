"""Cart tests run against fakeredis and an in-memory catalog behind httpx.MockTransport."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from app.core.config import Settings
from app.main import create_app, wire
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

SELLER_A = UUID("00000000-0000-0000-0000-00000000000a")
SELLER_B = UUID("00000000-0000-0000-0000-00000000000b")


@dataclass
class FakeCatalog:
    """Variants the fake catalog knows about, and every bulk request it received."""

    variants: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    requests: list[list[str]] = field(default_factory=list)
    down: bool = False

    def add(
        self,
        *,
        price: int = 10_000,
        available: int = 10,
        is_active: bool = True,
        seller_id: UUID = SELLER_A,
        shop_name: str = "Shop A",
        title: str = "T-shirt",
    ) -> UUID:
        variant_id = uuid4()
        self.variants[variant_id] = {
            "variant_id": str(variant_id),
            "product_id": str(uuid4()),
            "product_slug": f"product-{variant_id.hex[:6]}",
            "title": title,
            "sku": f"SKU-{variant_id.hex[:6]}",
            "price_tiyin": price,
            "available": available,
            "is_active": is_active,
            "seller_id": str(seller_id),
            "shop_name": shop_name,
            "image_url": None,
            "attributes": [{"code": "size", "name": "Size", "value": "M"}],
        }
        return variant_id

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(502)
        assert request.url.path == "/internal/catalog/variants/bulk/"
        ids = json.loads(request.content)["variant_ids"]
        self.requests.append(ids)
        items = [self.variants[UUID(raw)] for raw in ids if UUID(raw) in self.variants]
        return httpx.Response(200, json={"items": items})


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "redis_url": "redis://unused",
        "catalog_url": "http://catalog",
        "catalog_timeout": 1.0,
        "catalog_cache_seconds": 30,
        "cart_ttl_seconds": 30 * 24 * 3600,
        "max_qty": 99,
        "max_lines": 100,
        "max_favorites": 500,
        "guest_cookie": "guest_id",
        "guest_cookie_secure": False,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
async def redis() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def app(
    redis: FakeAsyncRedis, catalog: FakeCatalog, settings: Settings
) -> AsyncIterator[FastAPI]:
    application = create_app(with_lifespan=False)
    http = httpx.AsyncClient(
        base_url=settings.catalog_url, transport=httpx.MockTransport(catalog.handle)
    )
    wire(application, settings, redis, http)
    yield application
    await http.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def user_headers(user_id: UUID, role: str = "customer") -> dict[str, str]:
    return {"X-User-Id": str(user_id), "X-User-Role": role}
