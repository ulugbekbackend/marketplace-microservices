"""Gateway behaviour against the running stack (`make up`): routing, ForwardAuth, header hygiene.

Run with `make test-integration`. Needs DEBUG=True so the dev OTP master code works.
"""

import os
import random
from collections.abc import Iterator

import httpx
import pytest

GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1")
API_HOST = {"Host": "api.localhost"}
MASTER_CODE = "000000"

SERVICE_PREFIXES = [
    "/api/auth",
    "/api/catalog",
    "/api/orders",
    "/api/cart",
    "/api/search",
    "/api/payments",
    "/api/notifications",
]


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=GATEWAY, headers=API_HOST, timeout=10) as client:
        try:
            client.get("/api/auth/health/live")
        except httpx.TransportError:
            pytest.skip("stack is not running (make up)")
        yield client


@pytest.fixture(scope="module")
def access_token(client: httpx.Client) -> str:
    # A fresh number per run keeps the per-phone resend limit out of the way.
    phone = f"+99890{random.randint(1_000_000, 9_999_999)}"
    sent = client.post("/api/auth/otp/send/", json={"phone": phone})
    assert sent.status_code == 204, sent.text
    verified = client.post("/api/auth/otp/verify/", json={"phone": phone, "code": MASTER_CODE})
    assert verified.status_code == 200, verified.text
    token: str = verified.json()["access"]
    return token


@pytest.mark.parametrize("prefix", SERVICE_PREFIXES)
def test_health_is_public_for_every_service(client: httpx.Client, prefix: str) -> None:
    assert client.get(f"{prefix}/health/live").status_code == 200


@pytest.mark.parametrize(
    "path", ["/internal/catalog/variants/bulk/", "/internal/cart/abc", "/internal/orders/x/payable"]
)
def test_internal_routes_are_never_exposed(client: httpx.Client, path: str) -> None:
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/me/",
        "/api/catalog/seller/products/",
        "/api/orders/",
        "/api/payments/seller/payouts/",
    ],
)
def test_protected_routes_need_a_token(client: httpx.Client, path: str) -> None:
    assert client.get(path).status_code == 401


def test_spoofed_identity_headers_are_stripped(client: httpx.Client) -> None:
    spoofed = {
        "X-User-Id": "00000000-0000-0000-0000-000000000001",
        "X-User-Role": "admin",
    }
    response = client.get("/api/auth/me/", headers=spoofed)
    assert response.status_code == 401


def test_garbage_token_is_rejected(client: httpx.Client) -> None:
    response = client.get("/api/auth/me/", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_valid_token_reaches_the_service(client: httpx.Client, access_token: str) -> None:
    response = client.get("/api/auth/me/", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    assert response.json()["role"] == "customer"


def test_token_cannot_be_upgraded_with_a_spoofed_role(
    client: httpx.Client, access_token: str
) -> None:
    headers = {"Authorization": f"Bearer {access_token}", "X-User-Role": "admin"}
    response = client.get("/api/auth/admin/seller-applications/", headers=headers)
    assert response.status_code == 403


def test_optional_auth_lets_guests_through(client: httpx.Client) -> None:
    # jwt-optional: no token still reaches the service instead of a gateway 401.
    assert client.get("/api/cart/health/live").status_code == 200
    assert client.get("/api/catalog/health/live").status_code == 200


def test_cors_allows_only_the_frontends(client: httpx.Client) -> None:
    allowed = client.options(
        "/api/auth/otp/send/",
        headers={"Origin": "http://shop.localhost", "Access-Control-Request-Method": "POST"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://shop.localhost"

    other = client.options(
        "/api/auth/otp/send/",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert other.headers.get("access-control-allow-origin") is None
