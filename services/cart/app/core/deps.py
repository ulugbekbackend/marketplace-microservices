"""Request dependencies: services from app state and who owns the cart."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request, Response

from app.core.config import Settings
from app.services.cart import CartService
from app.services.store import CartOwner, FavoritesStore
from py_common.auth import CurrentUser
from py_common.web.fastapi import optional_user


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_cart_service(request: Request) -> CartService:
    service: CartService = request.app.state.cart_service
    return service


def get_favorites(request: Request) -> FavoritesStore:
    favorites: FavoritesStore = request.app.state.favorites
    return favorites


def read_guest_id(request: Request, settings: Settings) -> UUID | None:
    raw = request.cookies.get(settings.guest_cookie)
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def set_guest_cookie(response: Response, settings: Settings, guest_id: UUID) -> None:
    response.set_cookie(
        settings.guest_cookie,
        str(guest_id),
        max_age=settings.cart_ttl_seconds,
        path="/api/cart",
        httponly=True,
        secure=settings.guest_cookie_secure,
        samesite="lax",
    )


def delete_guest_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.guest_cookie,
        path="/api/cart",
        httponly=True,
        secure=settings.guest_cookie_secure,
        samesite="lax",
    )


def cart_owner(
    request: Request,
    response: Response,
    user: Annotated[CurrentUser | None, Depends(optional_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CartOwner:
    """A signed-in customer owns ``cart:user:*``; a guest gets an id cookie on first visit."""
    if user is not None:
        return CartOwner.user(user.user_id)
    guest_id = read_guest_id(request, settings)
    if guest_id is None:
        guest_id = uuid4()
        set_guest_cookie(response, settings, guest_id)
    return CartOwner.guest(guest_id)


Owner = Annotated[CartOwner, Depends(cart_owner)]
Carts = Annotated[CartService, Depends(get_cart_service)]
Favorites = Annotated[FavoritesStore, Depends(get_favorites)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
