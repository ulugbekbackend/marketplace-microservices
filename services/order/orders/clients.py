"""Synchronous clients for the cart and catalog internal APIs.

Any network failure, 5xx or malformed answer becomes ``ServiceUnavailable`` (API 503).
Business refusals (out of stock, nothing to commit) are returned or raised as typed
results so the use cases decide what they mean.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import httpx
from django.conf import settings

from contracts.headers import X_CORRELATION_ID
from py_common.context import get_correlation_id
from py_common.web.drf import ApiError

CART = "cart"
CATALOG = "catalog"
BULK_CHUNK = 200  # the catalog's limit per bulk call

#: Tests replace this with ``httpx.MockTransport``; ``None`` means real HTTP.
transport: httpx.BaseTransport | None = None


class ServiceUnavailable(ApiError):
    def __init__(self, service: str) -> None:
        super().__init__(
            "SERVICE_UNAVAILABLE",
            f"The {service} service is unavailable. Try again later.",
            status=503,
            details={"service": service},
        )
        self.service = service


class NotReserved(Exception):
    """The catalog holds no stock for the order, so there is nothing to commit."""


@dataclass(frozen=True, slots=True)
class CartLine:
    variant_id: UUID
    qty: int


@dataclass(frozen=True, slots=True)
class VariantInfo:
    variant_id: UUID
    title: str
    sku: str
    price_tiyin: int
    available: int
    is_active: bool
    seller_id: UUID
    shop_name: str
    commission_rate: Decimal
    image_url: str | None


@dataclass(frozen=True, slots=True)
class Reserved:
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ReserveRejected:
    code: str  # "OUT_OF_STOCK"
    variant_ids: list[UUID]


def _client(base_url: str) -> httpx.Client:
    headers = {}
    correlation_id = get_correlation_id()
    if correlation_id is not None:
        headers[X_CORRELATION_ID] = str(correlation_id)
    return httpx.Client(
        base_url=base_url,
        timeout=settings.INTERNAL_HTTP_TIMEOUT_SECONDS,
        transport=transport,
        headers=headers,
    )


def _call(service: str, base_url: str, method: str, path: str, body: Any = None) -> httpx.Response:
    try:
        with _client(base_url) as client:
            response = client.request(method, path, json=body)
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(service) from exc
    if response.status_code >= 500:
        raise ServiceUnavailable(service)
    return response


def _json(service: str, response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ServiceUnavailable(service) from exc


def _error_code(service: str, response: httpx.Response) -> tuple[str, dict[str, Any]]:
    body = _json(service, response)
    try:
        error = body["error"]
        return str(error["code"]), dict(error.get("details") or {})
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceUnavailable(service) from exc


def _expect_ok(service: str, response: httpx.Response) -> None:
    if not response.is_success:
        raise ServiceUnavailable(service)


# --- cart ---------------------------------------------------------------------------


def get_cart(user_id: UUID) -> list[CartLine]:
    """The customer's cart lines (quantities only; prices come from the catalog)."""
    response = _call(CART, settings.CART_INTERNAL_URL, "GET", f"/internal/cart/{user_id}")
    _expect_ok(CART, response)
    body = _json(CART, response)
    try:
        return [CartLine(UUID(str(item["variant_id"])), int(item["qty"])) for item in body["items"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceUnavailable(CART) from exc


def clear_cart(user_id: UUID) -> None:
    response = _call(CART, settings.CART_INTERNAL_URL, "DELETE", f"/internal/cart/{user_id}")
    _expect_ok(CART, response)


# --- catalog ------------------------------------------------------------------------


def variants_bulk(variant_ids: Iterable[UUID]) -> dict[UUID, VariantInfo]:
    """Current data of the variants; unknown ids are simply missing from the result."""
    ids = [str(variant_id) for variant_id in dict.fromkeys(variant_ids)]
    found: dict[UUID, VariantInfo] = {}
    for start in range(0, len(ids), BULK_CHUNK):
        chunk = ids[start : start + BULK_CHUNK]
        response = _call(
            CATALOG,
            settings.CATALOG_INTERNAL_URL,
            "POST",
            "/internal/catalog/variants/bulk/",
            {"variant_ids": chunk},
        )
        _expect_ok(CATALOG, response)
        body = _json(CATALOG, response)
        try:
            for item in body["items"]:
                info = _variant_info(item)
                found[info.variant_id] = info
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ServiceUnavailable(CATALOG) from exc
    return found


def _variant_info(item: dict[str, Any]) -> VariantInfo:
    return VariantInfo(
        variant_id=UUID(str(item["variant_id"])),
        title=str(item["title"]),
        sku=str(item["sku"]),
        price_tiyin=int(item["price_tiyin"]),
        available=int(item["available"]),
        is_active=bool(item["is_active"]),
        seller_id=UUID(str(item["seller_id"])),
        shop_name=str(item.get("shop_name") or ""),
        commission_rate=Decimal(str(item["commission_rate"])),
        image_url=item.get("image_url") or None,
    )


def reserve(order_id: UUID, items: Iterable[tuple[UUID, int]]) -> Reserved | ReserveRejected:
    """Hold stock for every item or none. A 409 comes back as ``ReserveRejected``."""
    response = _call(
        CATALOG,
        settings.CATALOG_INTERNAL_URL,
        "POST",
        "/internal/catalog/reservations/",
        {
            "order_id": str(order_id),
            "items": [{"variant_id": str(variant_id), "qty": qty} for variant_id, qty in items],
        },
    )
    if response.status_code == httpx.codes.CONFLICT:
        code, details = _error_code(CATALOG, response)
        try:
            variant_ids = [UUID(str(value)) for value in details.get("variant_ids", [])]
        except ValueError as exc:
            raise ServiceUnavailable(CATALOG) from exc
        return ReserveRejected(code, variant_ids)
    _expect_ok(CATALOG, response)
    body = _json(CATALOG, response)
    try:
        return Reserved(datetime.fromisoformat(str(body["expires_at"])))
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceUnavailable(CATALOG) from exc


def commit(order_id: UUID) -> None:
    """The order is paid: reserved units leave the stock. Idempotent on the catalog side."""
    response = _call(
        CATALOG,
        settings.CATALOG_INTERNAL_URL,
        "POST",
        f"/internal/catalog/reservations/{order_id}/commit/",
    )
    if response.status_code == httpx.codes.CONFLICT:
        code, _ = _error_code(CATALOG, response)
        if code == "NOT_RESERVED":
            raise NotReserved(str(order_id))
    _expect_ok(CATALOG, response)


def release(order_id: UUID) -> None:
    """Give reserved units back. Idempotent on the catalog side."""
    response = _call(
        CATALOG,
        settings.CATALOG_INTERNAL_URL,
        "POST",
        f"/internal/catalog/reservations/{order_id}/release/",
    )
    _expect_ok(CATALOG, response)
