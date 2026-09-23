"""Read-side querysets with the computed fields the API returns."""

from typing import Any

from django.db.models import Count, Exists, F, Max, Min, OuterRef, Prefetch, Q, QuerySet

from contracts.enums import ProductStatus
from products.models import Category, ImageStatus, Product, ProductImage, ProductVariant
from sellers.models import Seller

ACTIVE = ProductStatus.ACTIVE.value


def _with_prices(products: QuerySet[Product]) -> QuerySet[Product]:
    active_variant = Q(variants__is_active=True)
    sellable = ProductVariant.objects.filter(
        product=OuterRef("pk"), is_active=True, stock__gt=F("reserved")
    )
    return products.annotate(
        min_price_tiyin=Min("variants__price_tiyin", filter=active_variant),
        max_price_tiyin=Max("variants__price_tiyin", filter=active_variant),
        in_stock=Exists(sellable),
    )


def _ready_images() -> "Prefetch[Any]":
    return Prefetch(
        "images",
        queryset=ProductImage.objects.filter(status=ImageStatus.READY),
        to_attr="ready_images",
    )


def public_products() -> QuerySet[Product]:
    """Active products for the storefront list."""
    return (
        _with_prices(Product.objects.filter(status=ACTIVE))
        .select_related("seller", "category")
        .prefetch_related(_ready_images())
        .order_by("-created_at", "-id")
    )


def public_product_detail() -> QuerySet[Product]:
    variants = ProductVariant.objects.filter(is_active=True).prefetch_related(
        "attribute_values__attribute"
    )
    return public_products().prefetch_related(
        Prefetch("variants", queryset=variants, to_attr="active_variants")
    )


def seller_products(seller: Seller) -> QuerySet[Product]:
    """All of a seller's products in any status, with everything the seller UI shows."""
    variants = ProductVariant.objects.prefetch_related("attribute_values__attribute")
    return (
        _with_prices(Product.objects.filter(seller=seller))
        .annotate(variants_count=Count("variants", distinct=True))
        .select_related("seller", "category")
        .prefetch_related(
            _ready_images(),
            Prefetch("variants", queryset=variants, to_attr="all_variants"),
            Prefetch("images", queryset=ProductImage.objects.all(), to_attr="all_images"),
        )
        .order_by("-created_at", "-id")
    )


def shops() -> QuerySet[Seller]:
    return Seller.objects.annotate(
        product_count=Count("products", filter=Q(products__status=ACTIVE))
    )


def active_category_tree() -> list[dict[str, Any]]:
    """Nested active categories. An inactive category hides its whole subtree."""
    nodes: dict[Any, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for category in Category.objects.order_by("tree_id", "lft"):
        parent_node = nodes.get(category.parent_id) if category.parent_id else None
        if not category.is_active or (category.parent_id and parent_node is None):
            continue
        node = {"id": category.id, "name": category.name, "slug": category.slug, "children": []}
        nodes[category.id] = node
        (parent_node["children"] if parent_node else roots).append(node)
    return roots


def category_with_descendants(slug: str) -> QuerySet[Category] | None:
    category = Category.objects.filter(slug=slug, is_active=True).first()
    if category is None:
        return None
    descendants: QuerySet[Category] = category.get_descendants(include_self=True)
    return descendants.filter(is_active=True)
