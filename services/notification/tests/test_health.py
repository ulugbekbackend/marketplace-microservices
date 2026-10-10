"""The service answers liveness at the root and behind the gateway prefix."""

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from app.core.config import load_settings
from app.main import app, create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.parametrize("url", ["/health/live", "/api/notifications/health/live"])
async def test_liveness(client: AsyncClient, url: str) -> None:
    response = await client.get(url)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_metrics_are_exposed(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "python_info" in response.text


@pytest.mark.parametrize(
    ("rabbitmq_url", "checks"),
    [("amqp://user:pw@rabbitmq:5672/", {"redis", "rabbitmq"}), ("", {"redis"})],
)
async def test_readiness_reports_dependencies(rabbitmq_url: str, checks: set[str]) -> None:
    # Explicit settings: the result must not depend on the developer's .env.
    app = create_app(
        settings=replace(load_settings(), rabbitmq_url=rabbitmq_url), with_lifespan=False
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503  # not started: Redis is not connected
    assert set(response.json()["checks"]) == checks


async def test_correlation_id_is_returned(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.headers["X-Correlation-Id"]
