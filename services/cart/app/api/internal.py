"""Service-to-service endpoints for the order service.

Traefik routes only ``/api/cart``, so ``/internal`` is reachable on the internal network only.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.core.deps import Carts
from app.schemas import InternalCartItem, InternalCartOut
from app.services.store import CartOwner

router = APIRouter(prefix="/internal/cart", include_in_schema=False)


@router.get("/{user_id}", response_model=InternalCartOut)
async def get_user_cart(user_id: UUID, carts: Carts) -> InternalCartOut:
    """Raw quantities; the order service asks the catalog for prices itself."""
    lines = await carts.lines(CartOwner.user(user_id))
    return InternalCartOut(
        user_id=user_id,
        items=[InternalCartItem(variant_id=line.variant_id, qty=line.qty) for line in lines],
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_user_cart(user_id: UUID, carts: Carts) -> None:
    """Called by the order service once the order is paid."""
    await carts.clear(CartOwner.user(user_id))
