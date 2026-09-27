"""Cart use cases: the store keeps quantities, the catalog decides price and stock."""

from uuid import UUID

from app.schemas import CartItemOut, CartOut, SellerGroupOut
from app.services.catalog import CatalogClient, VariantInfo
from app.services.store import CartOwner, CartStore, StoredLine
from py_common.web.fastapi import ApiError


class CartService:
    def __init__(self, store: CartStore, catalog: CatalogClient, *, max_qty: int, max_lines: int):
        self._store = store
        self._catalog = catalog
        self._max_qty = max_qty
        self._max_lines = max_lines

    async def lines(self, owner: CartOwner) -> list[StoredLine]:
        return await self._store.lines(owner)

    async def view(self, owner: CartOwner) -> CartOut:
        lines = await self._store.lines(owner)
        variants = await self._catalog.variants(line.variant_id for line in lines)
        gone = [line.variant_id for line in lines if line.variant_id not in variants]
        await self._store.remove(owner, *gone)
        present = [line for line in lines if line.variant_id in variants]
        return build_cart(present, variants, removed=gone)

    async def add(self, owner: CartOwner, variant_id: UUID, qty: int) -> CartOut:
        current = await self._store.quantity(owner, variant_id)
        if current == 0 and await self._store.count_lines(owner) >= self._max_lines:
            raise ApiError(
                "CART_FULL",
                f"A cart holds at most {self._max_lines} different items.",
                status=409,
                details={"max_lines": self._max_lines},
            )
        wanted = min(current + qty, self._max_qty)
        variant = await self._sellable(variant_id, wanted)
        await self._store.set_line(owner, variant_id, wanted, variant.price_tiyin)
        return await self.view(owner)

    async def update(self, owner: CartOwner, variant_id: UUID, qty: int) -> CartOut:
        if await self._store.quantity(owner, variant_id) == 0:
            raise _not_in_cart(variant_id)
        if qty == 0:
            await self._store.remove(owner, variant_id)
        else:
            variant = await self._sellable(variant_id, qty)
            await self._store.set_line(owner, variant_id, qty, variant.price_tiyin)
        return await self.view(owner)

    async def remove(self, owner: CartOwner, variant_id: UUID) -> CartOut:
        if await self._store.quantity(owner, variant_id) == 0:
            raise _not_in_cart(variant_id)
        await self._store.remove(owner, variant_id)
        return await self.view(owner)

    async def clear(self, owner: CartOwner) -> None:
        await self._store.clear(owner)

    async def merge(self, guest: CartOwner, user: CartOwner) -> CartOut:
        await self._store.merge(guest, user)
        return await self.view(user)

    async def _sellable(self, variant_id: UUID, qty: int) -> VariantInfo:
        variant = await self._catalog.variant(variant_id)
        if variant is None:
            raise ApiError(
                "VARIANT_NOT_FOUND",
                "This product variant does not exist.",
                status=404,
                details={"variant_id": str(variant_id)},
            )
        if not variant.is_active:
            raise ApiError(
                "VARIANT_INACTIVE",
                "This product is not on sale.",
                status=409,
                details={"variant_id": str(variant_id)},
            )
        if variant.available < qty:
            raise ApiError(
                "OUT_OF_STOCK",
                "Not enough stock.",
                status=409,
                details={"variant_id": str(variant_id), "available": variant.available},
            )
        return variant


def _not_in_cart(variant_id: UUID) -> ApiError:
    return ApiError(
        "NOT_IN_CART",
        "This item is not in the cart.",
        status=404,
        details={"variant_id": str(variant_id)},
    )


def build_cart(
    lines: list[StoredLine], variants: dict[UUID, VariantInfo], *, removed: list[UUID]
) -> CartOut:
    """Group lines by seller (in the order sellers first appear) and total what can be bought."""
    groups: dict[UUID, SellerGroupOut] = {}
    for line in lines:
        variant = variants[line.variant_id]
        item = _item(line, variant)
        group = groups.get(variant.seller_id)
        if group is None:
            group = groups[variant.seller_id] = SellerGroupOut(
                seller_id=variant.seller_id, shop_name=variant.shop_name, items=[], subtotal_tiyin=0
            )
        group.items.append(item)
        if item.available:
            group.subtotal_tiyin += item.line_total_tiyin

    items = [item for group in groups.values() for item in group.items]
    return CartOut(
        groups=list(groups.values()),
        total_tiyin=sum(group.subtotal_tiyin for group in groups.values()),
        items_count=sum(item.qty for item in items),
        has_unavailable=any(not item.available for item in items),
        has_price_changes=any(item.price_changed for item in items),
        removed=removed,
    )


def _item(line: StoredLine, variant: VariantInfo) -> CartItemOut:
    changed = line.seen_price_tiyin is not None and line.seen_price_tiyin != variant.price_tiyin
    return CartItemOut(
        variant_id=variant.variant_id,
        product_id=variant.product_id,
        product_slug=variant.product_slug,
        title=variant.title,
        sku=variant.sku,
        image_url=variant.image_url,
        attributes=variant.attributes,
        qty=line.qty,
        price_tiyin=variant.price_tiyin,
        line_total_tiyin=variant.price_tiyin * line.qty,
        available_qty=max(variant.available, 0),
        available=variant.is_active and variant.available >= line.qty,
        price_changed=changed,
        previous_price_tiyin=line.seen_price_tiyin if changed else None,
    )
