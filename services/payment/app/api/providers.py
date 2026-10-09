"""Provider callbacks. The gateway routes them without JWT: Payme authenticates with
Basic Auth, Click with ``sign_string``."""

from typing import Any

from fastapi import APIRouter, Request

from app.core.deps import Click, Payme

router = APIRouter(prefix="/api/payments", tags=["providers"], include_in_schema=False)


@router.post("/payme/merchant")
async def payme_merchant(request: Request, payme: Payme) -> dict[str, Any]:
    """Payme Merchant API. Always HTTP 200; failures are JSON-RPC errors."""
    return await payme.handle(await request.body(), request.headers.get("authorization"))


async def _form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {key: value for key, value in form.items() if isinstance(value, str)}


@router.post("/click/prepare")
async def click_prepare(request: Request, click: Click) -> dict[str, Any]:
    return await click.prepare(await _form(request))


@router.post("/click/complete")
async def click_complete(request: Request, click: Click) -> dict[str, Any]:
    return await click.complete(await _form(request))
