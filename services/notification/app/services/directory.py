"""Who to notify. Events carry ids only; contacts come from auth, an order's customer from
the order service (both internal APIs).

    GET /internal/auth/users/{id}/contact/   -> {phone, full_name, email, telegram_chat_id}
    GET /internal/orders/{id}/payable/       -> {..., customer_id}
"""

from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError


class DirectoryUnavailableError(RuntimeError):
    """A lookup failed for a reason a retry may fix."""


class Contact(BaseModel):
    phone: str
    full_name: str = ""
    email: str = ""
    telegram_chat_id: str = ""


class _OrderOwner(BaseModel):
    customer_id: UUID


async def _get(http: httpx.AsyncClient, path: str) -> dict[str, object] | None:
    try:
        response = await http.get(path)
    except httpx.HTTPError as exc:
        raise DirectoryUnavailableError(str(exc)) from exc
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise DirectoryUnavailableError(f"{path} answered {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise DirectoryUnavailableError(f"{path} answered malformed JSON") from exc
    if not isinstance(body, dict):
        raise DirectoryUnavailableError(f"{path} answered malformed JSON")
    return body


class Directory:
    def __init__(self, auth: httpx.AsyncClient, orders: httpx.AsyncClient) -> None:
        self._auth = auth
        self._orders = orders

    async def contact(self, user_id: UUID) -> Contact | None:
        """None for an unknown or deactivated user: nobody to notify."""
        body = await _get(self._auth, f"/internal/auth/users/{user_id}/contact/")
        if body is None:
            return None
        try:
            return Contact.model_validate(body)
        except ValidationError as exc:
            raise DirectoryUnavailableError("malformed contact") from exc

    async def customer_of(self, order_id: UUID) -> UUID | None:
        body = await _get(self._orders, f"/internal/orders/{order_id}/payable/")
        if body is None:
            return None
        try:
            return _OrderOwner.model_validate(body).customer_id
        except ValidationError as exc:
            raise DirectoryUnavailableError("malformed order") from exc
