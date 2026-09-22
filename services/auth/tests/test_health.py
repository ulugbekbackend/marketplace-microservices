"""The service answers liveness at the root and behind the gateway prefix."""

import pytest
from django.test import Client


@pytest.mark.parametrize("url", ["/health/live", "/api/auth/health/live"])
def test_liveness(client: Client, url: str) -> None:
    response = client.get(url)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_are_exposed(client: Client) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"python_info" in response.content


def test_readiness_reports_dependencies(client: Client) -> None:
    response = client.get("/health/ready")

    assert response.status_code in (200, 503)
    assert "postgres" in response.json()["checks"]
