"""The service answers liveness at the root and behind the gateway prefix."""

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize("url", ["/health/live", "/api/payments/health/live"])
async def test_liveness(client: AsyncClient, url: str) -> None:
    response = await client.get(url)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_metrics_are_exposed(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "python_info" in response.text


async def test_readiness_checks_the_database(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert set(response.json()["checks"]) == {"postgres"}


async def test_correlation_id_is_returned(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.headers["X-Correlation-Id"]
