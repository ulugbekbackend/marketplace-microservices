"""Favorite products of a signed-in customer."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.deps import Favorites, SettingsDep
from app.schemas import FavoriteIn, FavoritesOut
from py_common.auth import CurrentUser
from py_common.web.fastapi import ApiError, required_user

router = APIRouter(prefix="/api/cart/favorites", tags=["favorites"])

User = Annotated[CurrentUser, Depends(required_user)]


@router.get("/", response_model=FavoritesOut)
async def list_favorites(user: User, favorites: Favorites) -> FavoritesOut:
    return FavoritesOut(items=await favorites.list(user.user_id))


@router.post("/", response_model=FavoritesOut)
async def add_favorite(
    body: FavoriteIn, user: User, favorites: Favorites, settings: SettingsDep
) -> FavoritesOut:
    """Idempotent: adding a product twice keeps one entry."""
    already = await favorites.contains(user.user_id, body.product_id)
    if not already and await favorites.count(user.user_id) >= settings.max_favorites:
        raise ApiError(
            "FAVORITES_FULL",
            f"At most {settings.max_favorites} favorites.",
            status=409,
            details={"max_favorites": settings.max_favorites},
        )
    await favorites.add(user.user_id, body.product_id)
    return FavoritesOut(items=await favorites.list(user.user_id))


@router.delete("/{product_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(product_id: UUID, user: User, favorites: Favorites) -> None:
    await favorites.remove(user.user_id, product_id)
