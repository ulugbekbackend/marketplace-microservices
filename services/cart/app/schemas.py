"""Request and response bodies of the cart API."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.services.catalog import VariantAttribute


class AddItemIn(BaseModel):
    variant_id: UUID
    qty: int = Field(default=1, ge=1, le=99)


class UpdateItemIn(BaseModel):
    qty: int = Field(ge=0, le=99, description="0 removes the item.")


class CartItemOut(BaseModel):
    variant_id: UUID
    product_id: UUID
    product_slug: str
    title: str
    sku: str
    image_url: str | None
    attributes: list[VariantAttribute]
    qty: int
    price_tiyin: int = Field(description="Current catalog price.")
    line_total_tiyin: int
    available_qty: int = Field(description="Units the catalog can still sell right now.")
    available: bool = Field(description="Active and enough stock for the requested quantity.")
    price_changed: bool = Field(description="The price differs from the one the customer saw.")
    previous_price_tiyin: int | None = Field(
        description="The price the customer saw, when it changed."
    )


class SellerGroupOut(BaseModel):
    seller_id: UUID
    shop_name: str
    items: list[CartItemOut]
    subtotal_tiyin: int = Field(description="Sum of the available items only.")


class CartOut(BaseModel):
    groups: list[SellerGroupOut]
    total_tiyin: int = Field(description="Sum of the available items only.")
    items_count: int = Field(description="Total quantity of all items.")
    has_unavailable: bool
    has_price_changes: bool
    removed: list[UUID] = Field(
        description="Variants dropped from the cart because they no longer exist."
    )


class FavoriteIn(BaseModel):
    product_id: UUID


class FavoritesOut(BaseModel):
    items: list[UUID]


class InternalCartItem(BaseModel):
    variant_id: UUID
    qty: int


class InternalCartOut(BaseModel):
    user_id: UUID
    items: list[InternalCartItem]
