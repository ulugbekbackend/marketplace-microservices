"""Health, metrics and the application lifespan."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from app.core.config import load_settings
from app.main import app, create_app, ensure_index_forever, make_elasticsearch
from app.services.index import ProductIndex
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from py_common.rabbit import broker_probe
from tests.conftest import closed_port_url, make_settings


@pytest.fixture
async def bare_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.parametrize("url", ["/health/live", "/api/search/health/live"])
async def test_liveness(bare_client: AsyncClient, url: str) -> None:
    response = await bare_client.get(url)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_metrics_are_exposed(bare_client: AsyncClient) -> None:
    response = await bare_client.get("/metrics")

    assert response.status_code == 200
    assert "search_latency_seconds" in response.text


async def test_not_ready_before_startup(bare_client: AsyncClient) -> None:
    response = await bare_client.get("/health/ready")

    assert response.status_code == 503
    assert set(response.json()["checks"]) == {"elasticsearch"}


async def test_correlation_id_is_returned(bare_client: AsyncClient) -> None:
    response = await bare_client.get("/health/live")

    assert response.headers["X-Correlation-Id"]


async def test_ready_when_elasticsearch_answers(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["elasticsearch"] == {"ok": True}


async def test_elasticsearch_down_is_not_ready_but_alive() -> None:
    application = create_app(with_lifespan=False)
    es = make_elasticsearch(make_settings("x", elasticsearch_url=closed_port_url()))
    application.state.es = es
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            ready = await client.get("/health/ready")
            live = await client.get("/health/live")
    finally:
        await es.close()

    assert ready.status_code == 503
    assert ready.json()["checks"]["elasticsearch"]["ok"] is False
    assert live.status_code == 200


async def test_search_with_elasticsearch_down_is_503() -> None:
    settings = make_settings("x", elasticsearch_url=closed_port_url(), elasticsearch_timeout=1.0)
    application = create_app(settings=settings)
    async with (
        application.router.lifespan_context(application),
        AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client,
    ):
        response = await client.get("/api/search", params={"q": "telefon"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SEARCH_UNAVAILABLE"


async def wait_for_index(index: ProductIndex) -> None:
    for _ in range(100):
        if (await index.targets()).live:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("index was not created")


async def test_lifespan_creates_the_index_and_serves(es: AsyncElasticsearch, alias: str) -> None:
    application: FastAPI = create_app(settings=make_settings(alias))
    async with (
        application.router.lifespan_context(application),
        AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client,
    ):
        await wait_for_index(ProductIndex(es, alias=alias))
        response = await client.get("/api/search")
        ready = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert ready.status_code == 200
    assert application.state.consumer is None


async def test_lifespan_starts_the_consumer_in_the_background(
    es: AsyncElasticsearch, alias: str
) -> None:
    # Nothing listens on the broker port: the API still starts and shuts down cleanly.
    broker = closed_port_url().replace("http://", "amqp://guest:guest@")
    settings = make_settings(alias, consumer_enabled=True, rabbitmq_url=broker)
    application = create_app(settings=settings)

    async with application.router.lifespan_context(application):
        await asyncio.sleep(0.1)
        assert application.state.consumer is not None
        assert not application.state.consumer.started.is_set()


async def test_index_bootstrap_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    class Flaky:
        async def ensure(self) -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("elasticsearch is starting")
            return "products_v1"

    await asyncio.wait_for(ensure_index_forever(Flaky(), 0.01), timeout=2)  # type: ignore[arg-type]

    assert attempts == 3


def test_settings_load_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_INDEX_ALIAS", "products_test")
    monkeypatch.setenv("SEARCH_CONSUMER_ENABLED", "false")

    settings = load_settings()

    assert settings.index_alias == "products_test"
    assert settings.consumer_enabled is False
    assert settings.reindex_page_size == 200


async def test_broker_probe_targets_the_url_host() -> None:
    probe = broker_probe(closed_port_url().replace("http://", "amqp://user:pw@"))

    with pytest.raises(OSError):
        await probe()
