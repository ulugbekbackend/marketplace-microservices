"""Cart service: guest and customer carts in Redis, favorites, internal API for orders."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from decouple import config
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api import cart, favorites, internal
from app.core.config import Settings, load_settings
from app.services.cart import CartService
from app.services.catalog import CatalogClient
from app.services.store import CartStore, FavoritesStore
from py_common.health import HealthRegistry, tcp_check
from py_common.logging import configure_logging
from py_common.web.fastapi import setup

SERVICE_NAME = "cart"
API_PREFIX = "/api/cart"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))


def build_registry() -> HealthRegistry:
    """Dependencies this service needs before it can serve traffic."""
    registry = HealthRegistry()
    registry.add(
        "redis",
        tcp_check(
            config("REDIS_HOST", default="redis"), config("REDIS_PORT", default=6379, cast=int)
        ),
    )
    return registry


def wire(app: FastAPI, settings: Settings, redis: Redis, http: httpx.AsyncClient) -> None:
    """Build the services once and keep them on the application state."""
    catalog = CatalogClient(http, redis, cache_seconds=settings.catalog_cache_seconds)
    store = CartStore(redis, ttl_seconds=settings.cart_ttl_seconds, max_qty=settings.max_qty)
    app.state.settings = settings
    app.state.cart_service = CartService(
        store, catalog, max_qty=settings.max_qty, max_lines=settings.max_lines
    )
    app.state.favorites = FavoritesStore(redis)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    http = httpx.AsyncClient(base_url=settings.catalog_url, timeout=settings.catalog_timeout)
    wire(app, settings, redis, http)
    try:
        yield
    finally:
        await http.aclose()
        await redis.aclose()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title="Cart service",
        version="0.2.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        lifespan=lifespan if with_lifespan else None,
    )
    setup(app, registry=build_registry(), api_prefix=API_PREFIX)
    app.include_router(favorites.router)
    app.include_router(cart.router)
    app.include_router(internal.router)
    return app


app = create_app()
