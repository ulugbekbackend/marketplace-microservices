"""Search service: product search over Elasticsearch, fed by catalog events."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from decouple import config
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api import internal, search
from app.consumers.products import (
    SERVICE,
    ConsumerRunner,
    ProductEventHandler,
    broker_probe,
    build_router,
)
from app.core.config import Settings, load_settings
from app.services.catalog import CatalogClient
from app.services.index import ProductIndex
from app.services.reindex import Reindexer
from app.services.search import SearchService
from py_common.health import CheckFn, HealthRegistry
from py_common.idempotency import RedisIdempotencyStore
from py_common.logging import configure_logging
from py_common.rabbit import AioPikaConsumer
from py_common.web.fastapi import setup

SERVICE_NAME = "search"
API_PREFIX = "/api/search"
BOOTSTRAP_RETRY_SECONDS = 5.0

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))
logger = logging.getLogger(__name__)


def elasticsearch_check(app: FastAPI) -> CheckFn:
    async def check() -> None:
        es: AsyncElasticsearch | None = getattr(app.state, "es", None)
        if es is None:
            raise RuntimeError("not started")
        await es.cluster.health(timeout="2s")

    return check


def build_registry(app: FastAPI) -> HealthRegistry:
    """Ready means Elasticsearch answers; without it there is nothing to search."""
    registry = HealthRegistry()
    registry.add("elasticsearch", elasticsearch_check(app))
    return registry


def make_elasticsearch(settings: Settings) -> AsyncElasticsearch:
    return AsyncElasticsearch(
        settings.elasticsearch_url,
        request_timeout=settings.elasticsearch_timeout,
        max_retries=1,
        retry_on_timeout=True,
    )


def wire(
    app: FastAPI,
    settings: Settings,
    es: AsyncElasticsearch,
    redis: Redis,
    http: httpx.AsyncClient,
) -> None:
    """Build the services once and keep them on the application state."""
    index = ProductIndex(
        es,
        alias=settings.index_alias,
        shards=settings.index_shards,
        replicas=settings.index_replicas,
    )
    store = RedisIdempotencyStore(redis, prefix=SERVICE)
    app.state.settings = settings
    app.state.es = es
    app.state.index = index
    app.state.search_service = SearchService(es, alias=settings.index_alias)
    app.state.reindexer = Reindexer(
        index,
        CatalogClient(http, page_size=settings.reindex_page_size),
        redis,
        lock_seconds=settings.reindex_lock_seconds,
    )
    app.state.event_handler = ProductEventHandler(build_router(index, store))


async def ensure_index_forever(index: ProductIndex, retry_seconds: float) -> None:
    """Create the index once Elasticsearch is reachable; the API runs meanwhile."""
    while True:
        try:
            await index.ensure()
            return
        except Exception:
            logger.warning("search index bootstrap failed, retrying", exc_info=True)
            await asyncio.sleep(retry_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = getattr(app.state, "initial_settings", None) or load_settings()
    es = make_elasticsearch(settings)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    http = httpx.AsyncClient(base_url=settings.catalog_url, timeout=settings.catalog_timeout)
    wire(app, settings, es, redis, http)
    bootstrap = asyncio.create_task(
        ensure_index_forever(app.state.index, BOOTSTRAP_RETRY_SECONDS), name="search-bootstrap"
    )
    runner: ConsumerRunner | None = None
    if settings.consumer_enabled and settings.rabbitmq_url:
        runner = ConsumerRunner(
            AioPikaConsumer(settings.rabbitmq_url, SERVICE, app.state.event_handler),
            probe=broker_probe(settings.rabbitmq_url),
        )
        runner.start()
    app.state.consumer = runner
    try:
        yield
    finally:
        bootstrap.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bootstrap
        if runner is not None:
            await runner.stop()
        await http.aclose()
        await redis.aclose()
        await es.close()


def create_app(*, with_lifespan: bool = True, settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Search service",
        version="0.2.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        lifespan=lifespan if with_lifespan else None,
    )
    app.state.initial_settings = settings
    setup(app, registry=build_registry(app), api_prefix=API_PREFIX)
    app.include_router(search.router)
    app.include_router(internal.router)
    return app


app = create_app()
