"""Shared fixtures. Tests run against real Postgres; cart and catalog are served by an
in-process fake behind ``httpx.MockTransport`` and Redis is fakeredis."""

import json
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import fakeredis
import httpx
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from contracts.enums import UserRole
from orders import clients, idempotency

CART_URL = "http://cart.test"
CATALOG_URL = "http://catalog.test"

ADDRESS = {
    "full_name": "Aziz Karimov",
    "phone": "+998901234567",
    "region": "Toshkent",
    "city": "Toshkent",
    "street": "Amir Temur 1",
}


def _error(status: int, code: str, details: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": code, "message": code, "details": details or {}}}
    )


class FakeUpstream:
    """Cart and catalog internal APIs with switchable failures.

    ``*_mode`` values: "ok", "down" (connection error), "error" (HTTP 500), plus
    "out_of_stock" for reserve and "not_reserved" for commit.
    """

    def __init__(self) -> None:
        self.carts: dict[UUID, list[dict[str, Any]]] = {}
        self.variants: dict[UUID, dict[str, Any]] = {}
        self.expires_at: datetime = timezone.now() + timedelta(minutes=15)
        self.cart_mode = "ok"
        self.clear_mode = "ok"
        self.bulk_mode = "ok"
        self.reserve_mode = "ok"
        self.commit_mode = "ok"
        self.release_mode = "ok"
        self.out_of_stock: list[UUID] = []
        self.calls: list[tuple[str, str]] = []
        self.requests: list[httpx.Request] = []
        self._lock = threading.Lock()

    # --- test helpers -------------------------------------------------------------------

    def add_variant(
        self,
        *,
        seller_id: UUID | None = None,
        price_tiyin: int = 1_000_000,
        available: int = 10,
        is_active: bool = True,
        commission_rate: str = "0.1000",
        title: str = "Phone",
        sku: str | None = None,
        shop_name: str = "Tech Shop",
        image_url: str | None = "http://minio.localhost/marketplace/thumb.webp",
    ) -> UUID:
        variant_id = uuid4()
        self.variants[variant_id] = {
            "variant_id": str(variant_id),
            "product_id": str(uuid4()),
            "product_slug": "phone",
            "title": title,
            "sku": sku or f"SKU-{str(variant_id)[:8]}",
            "price_tiyin": price_tiyin,
            "available": available,
            "is_active": is_active,
            "seller_id": str(seller_id or uuid4()),
            "shop_name": shop_name,
            "commission_rate": commission_rate,
            "image_url": image_url,
            "attributes": [],
        }
        return variant_id

    def put_in_cart(self, user_id: UUID, variant_id: UUID, qty: int = 1) -> None:
        self.carts.setdefault(user_id, []).append({"variant_id": str(variant_id), "qty": qty})

    def count(self, method: str, path_part: str) -> int:
        return sum(1 for m, path in self.calls if m == method and path_part in path)

    # --- transport ----------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.calls.append((request.method, request.url.path))
            self.requests.append(request)
        path = request.url.path
        if request.url.host == "cart.test":
            return self._cart(request, path)
        return self._catalog(request, path)

    def _fail(self, mode: str, request: httpx.Request) -> httpx.Response | None:
        if mode == "down":
            raise httpx.ConnectError("connection refused", request=request)
        if mode == "error":
            return httpx.Response(500, text="boom")
        return None

    def _cart(self, request: httpx.Request, path: str) -> httpx.Response:
        user_id = UUID(path.rstrip("/").rsplit("/", 1)[1])
        if request.method == "DELETE":
            failed = self._fail(self.clear_mode, request)
            if failed:
                return failed
            self.carts.pop(user_id, None)
            return httpx.Response(204)
        failed = self._fail(self.cart_mode, request)
        if failed:
            return failed
        return httpx.Response(
            200, json={"user_id": str(user_id), "items": self.carts.get(user_id, [])}
        )

    def _catalog(self, request: httpx.Request, path: str) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if path.endswith("/variants/bulk/"):
            failed = self._fail(self.bulk_mode, request)
            if failed:
                return failed
            items = [
                self.variants[UUID(vid)]
                for vid in body["variant_ids"]
                if UUID(vid) in self.variants
            ]
            return httpx.Response(200, json={"items": items})
        if path.endswith("/commit/"):
            failed = self._fail(self.commit_mode, request)
            if failed:
                return failed
            if self.commit_mode == "not_reserved":
                return _error(409, "NOT_RESERVED")
            return httpx.Response(200, json={"status": "committed", "items": []})
        if path.endswith("/release/"):
            failed = self._fail(self.release_mode, request)
            if failed:
                return failed
            return httpx.Response(200, json={"status": "released", "items": []})
        # reservations/
        failed = self._fail(self.reserve_mode, request)
        if failed:
            return failed
        if self.reserve_mode == "out_of_stock":
            return _error(409, "OUT_OF_STOCK", {"variant_ids": [str(v) for v in self.out_of_stock]})
        return httpx.Response(
            200,
            json={
                "order_id": body["order_id"],
                "status": "active",
                "expires_at": self.expires_at.isoformat(),
                "items": body["items"],
            },
        )


@pytest.fixture(autouse=True)
def upstream(settings: Any, monkeypatch: pytest.MonkeyPatch) -> FakeUpstream:
    settings.CART_INTERNAL_URL = CART_URL
    settings.CATALOG_INTERNAL_URL = CATALOG_URL
    fake = FakeUpstream()
    monkeypatch.setattr(clients, "transport", httpx.MockTransport(fake.handle))
    return fake


@pytest.fixture(autouse=True)
def redis_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[fakeredis.FakeRedis]:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(idempotency, "get_redis", lambda: client)
    yield client
    client.flushall()


@pytest.fixture
def mock_payments(settings: Any) -> None:
    settings.DEBUG = True
    settings.PAYMENT_MOCK_ENABLED = True


def user_client(user_id: UUID, role: UserRole = UserRole.CUSTOMER) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_USER_ID=str(user_id), HTTP_X_USER_ROLE=role.value)
    return client


@pytest.fixture
def customer_id() -> UUID:
    return uuid4()


@pytest.fixture
def api(customer_id: UUID) -> APIClient:
    return user_client(customer_id)


@pytest.fixture
def other_api() -> APIClient:
    return user_client(uuid4())


@pytest.fixture
def anonymous() -> APIClient:
    return APIClient()


def checkout(client: APIClient, key: str | None = "key-1", **body: Any) -> Any:
    headers: dict[str, Any] = {"HTTP_IDEMPOTENCY_KEY": key} if key is not None else {}
    return client.post(
        "/api/orders/checkout/", body or {"address": ADDRESS}, format="json", **headers
    )
