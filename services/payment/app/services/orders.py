"""The order service's internal API, as the payment service sees it.

Contract (order, internal network only):
    GET /internal/orders/{id}/payable/
        -> {"payable", "amount_tiyin", "status", "customer_id", "reserved_until"}
"""

import logging
from datetime import datetime
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class OrderUnavailableError(RuntimeError):
    """The order service did not answer, or answered something unexpected."""


class Payable(BaseModel):
    payable: bool
    amount_tiyin: int
    status: str
    customer_id: UUID
    reserved_until: datetime | None = None


class OrderClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def payable(self, order_id: UUID) -> Payable | None:
        """The order's payability, or None when no such order exists."""
        try:
            response = await self._http.get(f"/internal/orders/{order_id}/payable/")
        except httpx.HTTPError as exc:
            raise OrderUnavailableError(str(exc)) from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise OrderUnavailableError(f"order service answered {response.status_code}")
        try:
            return Payable.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise OrderUnavailableError("malformed payable answer") from exc
