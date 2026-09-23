"""Catalog data: category tree, products, variants with stock, images, reservations."""

from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from django.db import models
from django.db.models import F, Q, QuerySet
from mptt.models import MPTTModel

from contracts.enums import ProductStatus, ReservationStatus
from contracts.ids import uuid7
from sellers.models import Seller

PRODUCT_STATUS_CHOICES = [(status.value, status.name.title()) for status in ProductStatus]
RESERVATION_STATUS_CHOICES = [(status.value, status.name.title()) for status in ReservationStatus]


class ImageStatus(models.TextChoices):
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


if TYPE_CHECKING:
    # django-mptt ships no type hints: type-check the tree as a plain model and declare
    # the tree API used here below.
    _TreeModel = models.Model
else:
    _TreeModel = MPTTModel


class Category(_TreeModel):
    """Category tree (modified preorder traversal, django-mptt)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True)

    class MPTTMeta:
        order_insertion_by = ("name",)

    class Meta:
        verbose_name_plural = "categories"

    if TYPE_CHECKING:
        objects: ClassVar[models.Manager["Category"]]
        parent_id: UUID | None
        tree_id: int
        lft: int
        rght: int
        level: int

        def get_ancestors(
            self, ascending: bool = False, include_self: bool = False
        ) -> QuerySet["Category"]: ...

        def get_descendants(self, include_self: bool = False) -> QuerySet["Category"]: ...

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=PRODUCT_STATUS_CHOICES, default=ProductStatus.DRAFT.value
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = (
            models.Index(fields=["status", "-created_at"], name="product_status_created_idx"),
            models.Index(fields=["seller", "status"], name="product_seller_status_idx"),
        )

    def __str__(self) -> str:
        return self.title


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    original_key = models.CharField(max_length=255, unique=True)
    thumb_key = models.CharField(max_length=255, blank=True, default="")
    medium_key = models.CharField(max_length=255, blank=True, default="")
    large_key = models.CharField(max_length=255, blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16, choices=ImageStatus.choices, default=ImageStatus.PROCESSING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "created_at")

    def __str__(self) -> str:
        return self.original_key


class Attribute(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class AttributeValue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=80)

    class Meta:
        ordering = ("attribute__name", "value")
        constraints = (
            models.UniqueConstraint(fields=["attribute", "value"], name="attribute_value_unique"),
        )

    def __str__(self) -> str:
        return f"{self.attribute.code}={self.value}"


class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    price_tiyin = models.BigIntegerField()
    stock = models.IntegerField(default=0)
    reserved = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    attribute_values: "models.ManyToManyField[AttributeValue, VariantAttribute]" = (
        models.ManyToManyField(AttributeValue, through="VariantAttribute", related_name="variants")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = (
            models.CheckConstraint(condition=Q(price_tiyin__gt=0), name="variant_price_positive"),
            models.CheckConstraint(condition=Q(stock__gte=0), name="variant_stock_non_negative"),
            models.CheckConstraint(
                condition=Q(reserved__gte=0), name="variant_reserved_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(reserved__lte=F("stock")), name="variant_reserved_within_stock"
            ),
        )

    def __str__(self) -> str:
        return self.sku

    @property
    def available(self) -> int:
        return self.stock - self.reserved


class VariantAttribute(models.Model):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    attribute_value = models.ForeignKey(AttributeValue, on_delete=models.PROTECT)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["variant", "attribute_value"], name="variant_attribute_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.variant_id}:{self.attribute_value_id}"


class StockReservation(models.Model):
    """Stock held for an unpaid order. Reserve/commit/release logic arrives in P2."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    order_id = models.UUIDField()
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.PROTECT, related_name="reservations"
    )
    qty = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=RESERVATION_STATUS_CHOICES,
        default=ReservationStatus.ACTIVE.value,
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["order_id", "variant"], name="reservation_order_variant_unique"
            ),
            models.CheckConstraint(condition=Q(qty__gt=0), name="reservation_qty_positive"),
        )
        indexes = (
            models.Index(fields=["status", "expires_at"], name="reservation_status_expiry_idx"),
        )

    def __str__(self) -> str:
        return f"{self.order_id}:{self.variant_id}x{self.qty}"
