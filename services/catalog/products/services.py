"""Seller-side catalog changes. Each change and its outbox row commit together.

Lock order is always product row first, then variant or image rows, so concurrent
changes of one product serialize and each outbox document sees the previous change.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Max
from rest_framework.exceptions import NotFound

from contracts.enums import ProductStatus
from products.documents import record_product_change
from products.models import (
    AttributeValue,
    Category,
    ImageStatus,
    Product,
    ProductImage,
    ProductVariant,
    VariantAttribute,
)
from products.storage import IMAGE_EXTENSIONS, product_prefix
from py_common.web.drf import ApiError
from sellers.models import Seller
from slugs import unique_slug

logger = logging.getLogger(__name__)

PRODUCT_SLUG_MAX_LENGTH = 220
SLUG_ATTEMPTS = 5


def _not_found(what: str) -> NotFound:
    return NotFound(f"{what} not found.")


def _lock_product(seller: Seller, product_id: UUID) -> Product:
    """Lock one of the seller's products. Someone else's product is simply not found."""
    product = (
        Product.objects.select_for_update(of=("self",))
        .select_related("seller", "category")
        .filter(id=product_id, seller=seller)
        .first()
    )
    if product is None:
        raise _not_found("Product")
    return product


def _lock_variant(seller: Seller, variant_id: UUID) -> tuple[Product, ProductVariant]:
    product_id = (
        ProductVariant.objects.filter(id=variant_id, product__seller=seller)
        .values_list("product_id", flat=True)
        .first()
    )
    if product_id is None:
        raise _not_found("Variant")
    product = _lock_product(seller, product_id)
    variant = ProductVariant.objects.select_for_update().get(id=variant_id)
    return product, variant


def _touch(product: Product) -> None:
    """Bump ``updated_at``: a variant or image change is a change of the product."""
    product.save(update_fields=["updated_at"])


def _sku_taken(sku: str) -> ApiError:
    return ApiError("SKU_TAKEN", "This SKU is already used.", status=409, details={"sku": sku})


# --- products -----------------------------------------------------------------------


def create_product(
    seller: Seller,
    *,
    title: str,
    category: Category,
    description: str = "",
    status: str = ProductStatus.DRAFT.value,
) -> Product:
    with transaction.atomic():
        for attempt in range(SLUG_ATTEMPTS):
            slug = unique_slug(Product, title, max_length=PRODUCT_SLUG_MAX_LENGTH)
            try:
                with transaction.atomic():
                    product = Product.objects.create(
                        seller=seller,
                        category=category,
                        title=title,
                        slug=slug,
                        description=description,
                        status=status,
                    )
                break
            except IntegrityError:
                # A concurrent insert took the slug between the check and the insert.
                if attempt == SLUG_ATTEMPTS - 1:
                    raise
        record_product_change(product)
    return product


def update_product(
    seller: Seller,
    product_id: UUID,
    *,
    title: str | None = None,
    description: str | None = None,
    category: Category | None = None,
    status: str | None = None,
) -> Product:
    with transaction.atomic():
        product = _lock_product(seller, product_id)
        if title is not None:
            product.title = title
        if description is not None:
            product.description = description
        if category is not None:
            product.category = category
        if status is not None:
            product.status = status
        product.save()
        record_product_change(product)
    return product


def archive_product(seller: Seller, product_id: UUID) -> Product:
    """Soft delete: the product leaves the shop and the search index, data stays."""
    with transaction.atomic():
        product = _lock_product(seller, product_id)
        if product.status != ProductStatus.ARCHIVED.value:
            product.status = ProductStatus.ARCHIVED.value
            product.save(update_fields=["status", "updated_at"])
            record_product_change(product)
    return product


# --- variants -----------------------------------------------------------------------


def _resolve_attribute_values(ids: Iterable[UUID]) -> list[AttributeValue]:
    wanted = list(dict.fromkeys(ids))
    values = list(AttributeValue.objects.select_related("attribute").filter(id__in=wanted))
    missing = sorted(str(value_id) for value_id in set(wanted) - {value.id for value in values})
    if missing:
        raise ApiError(
            "VALIDATION_ERROR",
            "Unknown attribute values.",
            details={"attribute_value_ids": missing},
        )
    codes = [value.attribute.code for value in values]
    repeated = sorted({code for code in codes if codes.count(code) > 1})
    if repeated:
        raise ApiError(
            "VALIDATION_ERROR",
            "A variant takes one value per attribute.",
            details={"attribute_value_ids": [f"repeated attribute: {c}" for c in repeated]},
        )
    return values


def _combination_exists(product: Product, value_ids: frozenset[UUID]) -> bool:
    existing: dict[UUID, set[UUID]] = {
        variant_id: set() for variant_id in product.variants.values_list("id", flat=True)
    }
    for variant_id, value_id in VariantAttribute.objects.filter(
        variant__product=product
    ).values_list("variant_id", "attribute_value_id"):
        existing[variant_id].add(value_id)
    return any(frozenset(values) == value_ids for values in existing.values())


def create_variant(
    seller: Seller,
    product_id: UUID,
    *,
    sku: str,
    price_tiyin: int,
    stock: int,
    attribute_value_ids: Iterable[UUID] = (),
) -> ProductVariant:
    with transaction.atomic():
        product = _lock_product(seller, product_id)
        values = _resolve_attribute_values(attribute_value_ids)
        if _combination_exists(product, frozenset(value.id for value in values)):
            raise ApiError(
                "VARIANT_EXISTS",
                "The product already has a variant with these attribute values.",
                status=409,
            )
        if ProductVariant.objects.filter(sku=sku).exists():
            raise _sku_taken(sku)
        try:
            with transaction.atomic():
                variant = ProductVariant.objects.create(
                    product=product, sku=sku, price_tiyin=price_tiyin, stock=stock
                )
        except IntegrityError as exc:
            raise _sku_taken(sku) from exc
        VariantAttribute.objects.bulk_create(
            VariantAttribute(variant=variant, attribute_value=value) for value in values
        )
        _touch(product)
        record_product_change(product)
    return variant


def update_variant(
    seller: Seller,
    variant_id: UUID,
    *,
    sku: str | None = None,
    price_tiyin: int | None = None,
    is_active: bool | None = None,
) -> ProductVariant:
    with transaction.atomic():
        product, variant = _lock_variant(seller, variant_id)
        if sku is not None and sku != variant.sku:
            if ProductVariant.objects.filter(sku=sku).exclude(id=variant.id).exists():
                raise _sku_taken(sku)
            variant.sku = sku
        if price_tiyin is not None:
            variant.price_tiyin = price_tiyin
        if is_active is not None:
            variant.is_active = is_active
        try:
            with transaction.atomic():
                variant.save()
        except IntegrityError as exc:
            raise _sku_taken(variant.sku) from exc
        _touch(product)
        record_product_change(product)
    return variant


def set_variant_stock(seller: Seller, variant_id: UUID, stock: int) -> ProductVariant:
    """Set the on-hand quantity. It may never drop below what open orders hold."""
    with transaction.atomic():
        product, variant = _lock_variant(seller, variant_id)
        if stock < variant.reserved:
            raise ApiError(
                "STOCK_BELOW_RESERVED",
                "Stock cannot be lower than the quantity reserved by orders.",
                status=409,
                details={"reserved": variant.reserved},
            )
        variant.stock = stock
        variant.save(update_fields=["stock", "updated_at"])
        _touch(product)
        record_product_change(product)
    return variant


# --- images -------------------------------------------------------------------------


def ensure_own_product(seller: Seller, product_id: UUID) -> Product:
    product = Product.objects.filter(id=product_id, seller=seller).first()
    if product is None:
        raise _not_found("Product")
    return product


def _validate_image_key(product: Product, key: str) -> None:
    prefix = product_prefix(product.id)
    name = key.removeprefix(prefix)
    extension = name.rpartition(".")[2].lower()
    valid = (
        key.startswith(prefix)
        and bool(name)
        and "/" not in name
        and ".." not in name
        and extension in IMAGE_EXTENSIONS.values()
    )
    if not valid:
        raise ApiError(
            "INVALID_IMAGE_KEY",
            "The key does not belong to an upload for this product.",
            details={"key": key},
        )


def attach_image(seller: Seller, product_id: UUID, key: str) -> ProductImage:
    """Register an uploaded original; the worker turns it into WebP renditions."""
    from products.tasks import process_product_image

    with transaction.atomic():
        product = _lock_product(seller, product_id)
        _validate_image_key(product, key)
        if ProductImage.objects.filter(original_key=key).exists():
            raise ApiError("IMAGE_EXISTS", "This upload is already attached.", status=409)
        last = product.images.aggregate(last=Max("position"))["last"]
        image = ProductImage.objects.create(
            product=product,
            original_key=key,
            position=0 if last is None else last + 1,
            status=ImageStatus.PROCESSING,
        )
        _touch(product)
        record_product_change(product)
        image_id = str(image.id)
        transaction.on_commit(lambda: process_product_image.delay(image_id))
    return image


@dataclass(frozen=True, slots=True)
class RenditionKeys:
    thumb: str
    medium: str
    large: str


def _lock_image(image_id: UUID) -> tuple[Product, ProductImage] | None:
    product_id = (
        ProductImage.objects.filter(id=image_id).values_list("product_id", flat=True).first()
    )
    if product_id is None:
        return None
    product = (
        Product.objects.select_for_update(of=("self",))
        .select_related("seller", "category")
        .get(id=product_id)
    )
    image = ProductImage.objects.select_for_update().get(id=image_id)
    return product, image


def complete_image(image_id: UUID, keys: RenditionKeys) -> bool:
    """Mark an image ready and publish the product document. False if nothing changed."""
    with transaction.atomic():
        locked = _lock_image(image_id)
        if locked is None or locked[1].status != ImageStatus.PROCESSING:
            return False
        product, image = locked
        image.thumb_key = keys.thumb
        image.medium_key = keys.medium
        image.large_key = keys.large
        image.status = ImageStatus.READY
        image.save(update_fields=["thumb_key", "medium_key", "large_key", "status"])
        _touch(product)
        record_product_change(product)
    return True


def fail_image(image_id: UUID, reason: str) -> bool:
    with transaction.atomic():
        locked = _lock_image(image_id)
        if locked is None or locked[1].status != ImageStatus.PROCESSING:
            return False
        _, image = locked
        image.status = ImageStatus.FAILED
        image.save(update_fields=["status"])
    logger.warning("product image rejected", extra={"image_id": str(image_id), "reason": reason})
    return True
