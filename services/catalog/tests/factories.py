"""Model factories. Tests call the typed ``make_*`` helpers."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

from django.utils import timezone
from factory.declarations import LazyAttribute, LazyFunction, SelfAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from contracts.enums import ProductStatus
from products.models import (
    Attribute,
    AttributeValue,
    Category,
    ImageStatus,
    Product,
    ProductImage,
    ProductVariant,
    StockReservation,
)
from sellers.models import Seller


class SellerFactory(DjangoModelFactory[Seller]):
    class Meta:
        model = Seller

    id = LazyFunction(uuid4)  # type: ignore[no-untyped-call]
    user_id = SelfAttribute("id")  # type: ignore[no-untyped-call]
    shop_name = Sequence(lambda n: f"Shop {n}")  # type: ignore[no-untyped-call]
    slug = Sequence(lambda n: f"shop-{n}")  # type: ignore[no-untyped-call]
    is_verified = True


class CategoryFactory(DjangoModelFactory[Category]):
    class Meta:
        model = Category

    name = Sequence(lambda n: f"Category {n}")  # type: ignore[no-untyped-call]
    slug = Sequence(lambda n: f"category-{n}")  # type: ignore[no-untyped-call]
    parent = None
    is_active = True


class ProductFactory(DjangoModelFactory[Product]):
    class Meta:
        model = Product

    seller = SubFactory(SellerFactory)  # type: ignore[no-untyped-call]
    category = SubFactory(CategoryFactory)  # type: ignore[no-untyped-call]
    title = Sequence(lambda n: f"Product {n}")  # type: ignore[no-untyped-call]
    slug = Sequence(lambda n: f"product-{n}")  # type: ignore[no-untyped-call]
    description = "A fine product."
    status = ProductStatus.ACTIVE.value


class AttributeFactory(DjangoModelFactory[Attribute]):
    class Meta:
        model = Attribute

    name = Sequence(lambda n: f"Attribute {n}")  # type: ignore[no-untyped-call]
    code = Sequence(lambda n: f"attr{n}")  # type: ignore[no-untyped-call]


class AttributeValueFactory(DjangoModelFactory[AttributeValue]):
    class Meta:
        model = AttributeValue

    attribute = SubFactory(AttributeFactory)  # type: ignore[no-untyped-call]
    value = Sequence(lambda n: f"value-{n}")  # type: ignore[no-untyped-call]


class VariantFactory(DjangoModelFactory[ProductVariant]):
    class Meta:
        model = ProductVariant

    product = SubFactory(ProductFactory)  # type: ignore[no-untyped-call]
    sku = Sequence(lambda n: f"SKU-{n:05d}")  # type: ignore[no-untyped-call]
    price_tiyin = 1_000_000
    stock = 10
    reserved = 0
    is_active = True


def _rendition(name: str) -> Any:
    return LazyAttribute(  # type: ignore[no-untyped-call]
        lambda o: o.original_key.replace(".jpg", f"_{name}.webp")
    )


class ImageFactory(DjangoModelFactory[ProductImage]):
    class Meta:
        model = ProductImage

    product = SubFactory(ProductFactory)  # type: ignore[no-untyped-call]
    original_key = LazyAttribute(  # type: ignore[no-untyped-call]
        lambda o: f"products/{o.product.id}/{uuid4()}.jpg"
    )
    status = ImageStatus.READY
    thumb_key = _rendition("thumb")
    medium_key = _rendition("medium")
    large_key = _rendition("large")
    position = 0


class ReservationFactory(DjangoModelFactory[StockReservation]):
    class Meta:
        model = StockReservation

    order_id = LazyFunction(uuid4)  # type: ignore[no-untyped-call]
    variant = SubFactory(VariantFactory)  # type: ignore[no-untyped-call]
    qty = 1
    expires_at = LazyFunction(  # type: ignore[no-untyped-call]
        lambda: timezone.now() + timedelta(minutes=15)
    )


def make_seller(**fields: Any) -> Seller:
    return SellerFactory.create(**fields)


def make_category(**fields: Any) -> Category:
    return CategoryFactory.create(**fields)


def make_product(**fields: Any) -> Product:
    return ProductFactory.create(**fields)


def make_attribute_value(**fields: Any) -> AttributeValue:
    return AttributeValueFactory.create(**fields)


def make_variant(**fields: Any) -> ProductVariant:
    return VariantFactory.create(**fields)


def make_image(**fields: Any) -> ProductImage:
    return ImageFactory.create(**fields)


def make_reservation(**fields: Any) -> StockReservation:
    return ReservationFactory.create(**fields)
