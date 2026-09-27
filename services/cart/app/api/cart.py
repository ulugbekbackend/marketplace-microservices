"""Public cart endpoints: guests and signed-in customers (jwt-optional at the gateway)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.deps import Carts, Owner, SettingsDep, delete_guest_cookie, read_guest_id
from app.schemas import AddItemIn, CartOut, UpdateItemIn
from app.services.store import CartOwner
from py_common.auth import CurrentUser
from py_common.web.fastapi import required_user

router = APIRouter(prefix="/api/cart", tags=["cart"])


@router.get("/", response_model=CartOut)
async def get_cart(owner: Owner, carts: Carts) -> CartOut:
    """Items grouped by seller, with the current price and stock from the catalog."""
    return await carts.view(owner)


@router.post("/items/", response_model=CartOut)
async def add_item(body: AddItemIn, owner: Owner, carts: Carts) -> CartOut:
    """Add units of a variant; an item already in the cart grows (up to 99)."""
    return await carts.add(owner, body.variant_id, body.qty)


@router.patch("/items/{variant_id}/", response_model=CartOut)
async def update_item(variant_id: UUID, body: UpdateItemIn, owner: Owner, carts: Carts) -> CartOut:
    """Set the quantity; 0 removes the item."""
    return await carts.update(owner, variant_id, body.qty)


@router.delete("/items/{variant_id}/", response_model=CartOut)
async def remove_item(variant_id: UUID, owner: Owner, carts: Carts) -> CartOut:
    return await carts.remove(owner, variant_id)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(owner: Owner, carts: Carts) -> None:
    await carts.clear(owner)


@router.post("/merge/", response_model=CartOut)
async def merge_cart(
    request: Request,
    response: Response,
    user: Annotated[CurrentUser, Depends(required_user)],
    carts: Carts,
    settings: SettingsDep,
) -> CartOut:
    """Right after login: move the guest cart (cookie) into the customer's cart."""
    target = CartOwner.user(user.user_id)
    guest_id = read_guest_id(request, settings)
    if guest_id is None:
        return await carts.view(target)
    delete_guest_cookie(response, settings)
    return await carts.merge(CartOwner.guest(guest_id), target)
