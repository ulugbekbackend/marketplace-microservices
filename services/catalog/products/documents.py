"""Product events: every change leaves one outbox row describing the product for search."""

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from django.db.models import Count, F, Max, Min, Q
from django.utils import timezone

from contracts.enums import ProductStatus
from contracts.events import ProductAttribute, ProductDeleted, ProductUpdated, build_event
from messaging.models import Outbox
from messaging.outbox import add_to_outbox
from products.models import (
    Category,
    ImageStatus,
    Product,
    ProductImage,
    ProductVariant,
    VariantAttribute,
)
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


def _category_chains(category_ids: set[UUID]) -> dict[UUID, list[Category]]:
    fresh = Category.objects.filter(pk__in=category_ids)
    return {category.pk: list(category.get_ancestors(include_self=True)) for category in fresh}


def build_product_documents(products: Sequence[Product]) -> list[ProductUpdated]:
    """Search documents of many products, read from the current transaction.

    The number of queries depends on how many distinct categories the products sit in,
    not on how many products there are. Pass products with ``seller`` selected.
    """
    ids = [product.id for product in products]

    stats = {
        row["product_id"]: row
        for row in ProductVariant.objects.filter(product_id__in=ids, is_active=True)
        .values("product_id")
        .annotate(
            low=Min("price_tiyin"),
            high=Max("price_tiyin"),
            in_stock=Count("id", filter=Q(stock__gt=F("reserved"))),
        )
        .order_by()
    }

    attributes: dict[UUID, list[ProductAttribute]] = defaultdict(list)
    attribute_rows = (
        VariantAttribute.objects.filter(variant__product_id__in=ids, variant__is_active=True)
        .values_list(
            "variant__product_id", "attribute_value__attribute__code", "attribute_value__value"
        )
        .distinct()
        .order_by(
            "variant__product_id", "attribute_value__attribute__code", "attribute_value__value"
        )
    )
    for product_id, code, value in attribute_rows:
        attributes[product_id].append(ProductAttribute(code=code, value=value))

    images: dict[UUID, ProductImage] = {}
    for image in ProductImage.objects.filter(product_id__in=ids, status=ImageStatus.READY).order_by(
        "product_id", "position", "created_at"
    ):
        images.setdefault(image.product_id, image)

    chains = _category_chains({product.category_id for product in products})

    documents = []
    for product in products:
        row = stats.get(product.id, {})
        chain = chains[product.category_id]
        first_image = images.get(product.id)
        documents.append(
            ProductUpdated(
                product_id=product.id,
                seller_id=product.seller.id,
                shop_name=product.seller.shop_name,
                title=product.title,
                slug=product.slug,
                description=product.description,
                category_ids=[category.id for category in chain],
                category_path=[category.name for category in chain],
                min_price_tiyin=row.get("low") or 0,
                max_price_tiyin=row.get("high") or 0,
                in_stock=bool(row.get("in_stock")),
                attributes=attributes.get(product.id, []),
                rating=0.0,
                image_url=public_url(first_image.medium_key) if first_image else None,
                created_at=product.created_at,
                updated_at=product.updated_at,
            )
        )
    return documents


def build_product_document(product: Product) -> ProductUpdated:
    """The full search document of one product, read from the current transaction."""
    [document] = build_product_documents([product])
    return document


def record_product_change(product: Product, *, correlation_id: UUID | None = None) -> Outbox:
    """Write ``product.updated`` for an active product, ``product.deleted`` otherwise.

    Must run in the transaction of the change: the outbox helper refuses autocommit.
    The correlation id defaults to the product id; event driven changes pass the id of
    the flow that caused them.
    """
    payload: ProductUpdated | ProductDeleted
    if is_indexable(product):
        payload = build_product_document(product)
    else:
        payload = ProductDeleted(product_id=product.id)
    envelope = build_event(
        payload,
        producer=PRODUCER,
        correlation_id=correlation_id or product.id,
        occurred_at=timezone.now(),
    )
    return add_to_outbox(envelope)
