"""Request and response shapes of the catalog API (also the OpenAPI components)."""

from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from contracts.enums import ProductStatus
from products.documents import category_chain
from products.models import (
    PRODUCT_STATUS_CHOICES,
    Attribute,
    AttributeValue,
    Category,
    Product,
    ProductImage,
    ProductVariant,
)
from products.storage import IMAGE_CONTENT_TYPE_CHOICES, public_url
from sellers.models import Seller

SKU_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

# --- shared pieces ------------------------------------------------------------------


class CategoryNodeSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        fields = super().get_fields()
        fields["children"] = CategoryNodeSerializer(many=True)
        return fields


class CategoryRefSerializer(serializers.ModelSerializer[Category]):
    class Meta:
        model = Category
        fields = ("id", "name", "slug")


class SellerCardSerializer(serializers.ModelSerializer[Seller]):
    class Meta:
        model = Seller
        fields = ("id", "slug", "shop_name", "is_verified")


class ShopSerializer(serializers.ModelSerializer[Seller]):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Seller
        fields = ("id", "slug", "shop_name", "is_verified", "created_at", "product_count")


class AttributeValueSerializer(serializers.ModelSerializer[AttributeValue]):
    class Meta:
        model = AttributeValue
        fields = ("id", "value")


class AttributeSerializer(serializers.ModelSerializer[Attribute]):
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = Attribute
        fields = ("id", "name", "code", "values")


class VariantAttributeSerializer(serializers.ModelSerializer[AttributeValue]):
    """One attribute value of a variant, e.g. color = red."""

    value_id = serializers.UUIDField(source="id", read_only=True)
    code = serializers.CharField(source="attribute.code", read_only=True)
    name = serializers.CharField(source="attribute.name", read_only=True)

    class Meta:
        model = AttributeValue
        fields = ("value_id", "code", "name", "value")


class ImageSerializer(serializers.ModelSerializer[ProductImage]):
    thumb_url = serializers.SerializerMethodField()
    medium_url = serializers.SerializerMethodField()
    large_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields: tuple[str, ...] = ("id", "position", "thumb_url", "medium_url", "large_url")

    def get_thumb_url(self, image: ProductImage) -> str | None:
        return public_url(image.thumb_key)

    def get_medium_url(self, image: ProductImage) -> str | None:
        return public_url(image.medium_key)

    def get_large_url(self, image: ProductImage) -> str | None:
        return public_url(image.large_key)


class SellerImageSerializer(ImageSerializer):
    class Meta(ImageSerializer.Meta):
        fields = (*ImageSerializer.Meta.fields, "status", "original_key", "created_at")


def _first_image_url(product: Product) -> str | None:
    images: list[ProductImage] = getattr(product, "ready_images", [])
    return public_url(images[0].medium_key) if images else None


class _PricedProductFields(serializers.Serializer[Product]):
    min_price_tiyin = serializers.IntegerField(
        read_only=True, allow_null=True, help_text="Lowest active variant price, tiyin."
    )
    max_price_tiyin = serializers.IntegerField(
        read_only=True, allow_null=True, help_text="Highest active variant price, tiyin."
    )
    in_stock = serializers.BooleanField(read_only=True)
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, product: Product) -> str | None:
        return _first_image_url(product)


# --- public -------------------------------------------------------------------------


class PublicVariantSerializer(serializers.ModelSerializer[ProductVariant]):
    available = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    attributes = VariantAttributeSerializer(source="attribute_values", many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ("id", "sku", "price_tiyin", "available", "in_stock", "attributes")

    def get_available(self, variant: ProductVariant) -> int:
        """Units a customer can still buy: stock not held by an active reservation."""
        return max(variant.available, 0)

    def get_in_stock(self, variant: ProductVariant) -> bool:
        return variant.available > 0


class ProductCardSerializer(_PricedProductFields, serializers.ModelSerializer[Product]):
    seller = SellerCardSerializer(read_only=True)
    category = CategoryRefSerializer(read_only=True)

    class Meta:
        model = Product
        fields: tuple[str, ...] = (
            "id",
            "slug",
            "title",
            "min_price_tiyin",
            "max_price_tiyin",
            "in_stock",
            "image_url",
            "seller",
            "category",
            "created_at",
        )


class ProductDetailSerializer(ProductCardSerializer):
    variants = PublicVariantSerializer(source="active_variants", many=True, read_only=True)
    images = ImageSerializer(source="ready_images", many=True, read_only=True)
    breadcrumbs = serializers.SerializerMethodField()

    class Meta(ProductCardSerializer.Meta):
        fields = (
            *ProductCardSerializer.Meta.fields,
            "description",
            "breadcrumbs",
            "variants",
            "images",
            "updated_at",
        )

    @extend_schema_field(CategoryRefSerializer(many=True))
    def get_breadcrumbs(self, product: Product) -> list[dict[str, Any]]:
        chain = category_chain(product.category)
        return list(CategoryRefSerializer(chain, many=True).data)


# --- seller: responses --------------------------------------------------------------


class SellerVariantSerializer(serializers.ModelSerializer[ProductVariant]):
    available = serializers.IntegerField(read_only=True, help_text="stock - reserved")
    attributes = VariantAttributeSerializer(source="attribute_values", many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "sku",
            "price_tiyin",
            "stock",
            "reserved",
            "available",
            "is_active",
            "attributes",
            "created_at",
            "updated_at",
        )


class SellerProductSerializer(_PricedProductFields, serializers.ModelSerializer[Product]):
    category = CategoryRefSerializer(read_only=True)
    variants_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields: tuple[str, ...] = (
            "id",
            "slug",
            "title",
            "status",
            "category",
            "min_price_tiyin",
            "max_price_tiyin",
            "in_stock",
            "variants_count",
            "image_url",
            "created_at",
            "updated_at",
        )


class SellerProductDetailSerializer(SellerProductSerializer):
    variants = SellerVariantSerializer(source="all_variants", many=True, read_only=True)
    images = SellerImageSerializer(source="all_images", many=True, read_only=True)

    class Meta(SellerProductSerializer.Meta):
        fields = (*SellerProductSerializer.Meta.fields, "description", "variants", "images")


# --- seller: requests ---------------------------------------------------------------


class ProductCreateSerializer(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True), help_text="An active category."
    )
    status = serializers.ChoiceField(
        choices=PRODUCT_STATUS_CHOICES,
        default=ProductStatus.DRAFT.value,
        help_text="draft or active; a new product cannot start archived.",
    )

    def validate_status(self, value: str) -> str:
        if value == ProductStatus.ARCHIVED.value:
            raise serializers.ValidationError("A new product cannot be archived.")
        return value


class ProductUpdateSerializer(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True), required=False
    )
    status = serializers.ChoiceField(choices=PRODUCT_STATUS_CHOICES, required=False)


class VariantCreateSerializer(serializers.Serializer[Any]):
    sku = serializers.RegexField(SKU_PATTERN, max_length=64)
    price_tiyin = serializers.IntegerField(min_value=1, help_text="Price in tiyin.")
    stock = serializers.IntegerField(min_value=0)
    attribute_value_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=20
    )


class VariantUpdateSerializer(serializers.Serializer[Any]):
    sku = serializers.RegexField(SKU_PATTERN, max_length=64, required=False)
    price_tiyin = serializers.IntegerField(min_value=1, required=False)
    is_active = serializers.BooleanField(required=False)


class StockUpdateSerializer(serializers.Serializer[Any]):
    stock = serializers.IntegerField(min_value=0)


class PresignRequestSerializer(serializers.Serializer[Any]):
    product_id = serializers.UUIDField(help_text="The seller's product the image is for.")
    filename = serializers.CharField(max_length=255)
    content_type = serializers.ChoiceField(choices=IMAGE_CONTENT_TYPE_CHOICES)
    size = serializers.IntegerField(min_value=1, help_text="File size in bytes.")

    def validate_size(self, size: int) -> int:
        limit: int = settings.IMAGE_MAX_UPLOAD_BYTES
        if size > limit:
            raise serializers.ValidationError(f"The file must not be larger than {limit} bytes.")
        return size


class PresignResponseSerializer(serializers.Serializer[Any]):
    upload_url = serializers.URLField(help_text="PUT the file here.")
    key = serializers.CharField(help_text="Send it to the images endpoint after the upload.")
    headers = serializers.DictField(
        child=serializers.CharField(), help_text="Headers the PUT request must carry."
    )
    method = serializers.CharField()
    expires_in = serializers.IntegerField(help_text="Seconds the URL stays valid.")


class ImageAttachSerializer(serializers.Serializer[Any]):
    key = serializers.CharField(max_length=255)
