"""Product events: every change leaves one outbox row describing the product for search."""

from django.db.models import Max, Min
from django.utils import timezone

from contracts.enums import ProductStatus
from contracts.events import ProductAttribute, ProductDeleted, ProductUpdated, build_event
from messaging.models import Outbox
from messaging.outbox import add_to_outbox
from products.models import Category, ImageStatus, Product, ProductImage, VariantAttribute
from products.storage import public_url

PRODUCER = "catalog"


def is_indexable(product: Product) -> bool:
    return product.status == ProductStatus.ACTIVE.value


def category_chain(category: Category) -> list[Category]:
    """Root first, the category itself last.

    Tree bounds are re-read: inserting other categories shifts them, so an instance
    loaded earlier may point at the wrong nodes.
    """
    fresh = Category.objects.get(pk=category.pk)
    return list(fresh.get_ancestors(include_self=True))


def first_ready_image(product: Product) -> ProductImage | None:
    return (
        ProductImage.objects.filter(product=product, status=ImageStatus.READY)
        .order_by("position", "created_at")
        .first()
    )


def build_product_document(product: Product) -> ProductUpdated:
    """The full search document of a product, read from the current transaction."""
    variants = product.variants.filter(is_active=True)
    prices = variants.aggregate(low=Min("price_tiyin"), high=Max("price_tiyin"))
    in_stock = any(
        stock > reserved for stock, reserved in variants.values_list("stock", "reserved")
    )
    attribute_pairs = (
        VariantAttribute.objects.filter(variant__in=variants)
        .values_list("attribute_value__attribute__code", "attribute_value__value")
        .distinct()
        .order_by("attribute_value__attribute__code", "attribute_value__value")
    )
    chain = category_chain(product.category)
    image = first_ready_image(product)

    return ProductUpdated(
        product_id=product.id,
        seller_id=product.seller.id,
        shop_name=product.seller.shop_name,
        title=product.title,
        slug=product.slug,
        description=product.description,
        category_ids=[category.id for category in chain],
        category_path=[category.name for category in chain],
        min_price_tiyin=prices["low"] or 0,
        max_price_tiyin=prices["high"] or 0,
        in_stock=in_stock,
        attributes=[ProductAttribute(code=code, value=value) for code, value in attribute_pairs],
        rating=0.0,
        image_url=public_url(image.medium_key) if image else None,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def record_product_change(product: Product) -> Outbox:
    """Write ``product.updated`` for an active product, ``product.deleted`` otherwise.

    Must run in the transaction of the change: the outbox helper refuses autocommit.
    """
    payload: ProductUpdated | ProductDeleted
    if is_indexable(product):
        payload = build_product_document(product)
    else:
        payload = ProductDeleted(product_id=product.id)
    envelope = build_event(
        payload,
        producer=PRODUCER,
        correlation_id=product.id,
        occurred_at=timezone.now(),
    )
    return add_to_outbox(envelope)
