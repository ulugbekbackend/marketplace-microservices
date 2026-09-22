"""The service answers liveness at the root and behind the gateway prefix."""

from collections.abc import AsyncIterator

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.parametrize("url", ["/health/live", "/api/cart/health/live"])
async def test_liveness(client: AsyncClient, url: str) -> None:
    response = await client.get(url)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_metrics_are_exposed(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "python_info" in response.text


async def test_readiness_reports_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code in (200, 503)
    assert set(response.json()["checks"]) == {"redis"}


async def test_correlation_id_is_returned(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.headers["X-Correlation-Id"]
