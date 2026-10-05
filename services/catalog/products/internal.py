"""Service-to-service API (cart, order, search). Traefik routes only ``/api/catalog``, so
``/internal/catalog`` is reachable on the internal network only.

    POST /internal/catalog/variants/bulk/     {variant_ids} -> {items}
    GET  /internal/catalog/search-documents/  ?page=&page_size= -> paginated documents

Stock reservation is event driven (``messaging.handlers``), not part of this API.
"""

from typing import Any

from django.db.models import Prefetch
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from contracts.enums import ProductStatus
from products.documents import build_product_documents
from products.models import ImageStatus, Product, ProductImage, ProductVariant
from products.storage import public_url

MAX_BULK = 200
DEFAULT_DOCUMENTS_PAGE = 200
MAX_DOCUMENTS_PAGE = 500


# --- variants bulk ----------------------------------------------------------------------


class BulkRequestSerializer(serializers.Serializer[Any]):
    variant_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=True, max_length=MAX_BULK
    )


def variant_info(variant: ProductVariant) -> dict[str, Any]:
    """Everything a cart line or an order snapshot needs about one variant."""
    product = variant.product
    seller = product.seller
    images: list[ProductImage] = getattr(product, "ready_images", [])
    return {
        "variant_id": str(variant.id),
        "product_id": str(product.id),
        "product_slug": product.slug,
        "title": product.title,
        "sku": variant.sku,
        "price_tiyin": variant.price_tiyin,
        "available": max(variant.available, 0),
        "is_active": variant.is_active and product.status == ProductStatus.ACTIVE.value,
        "seller_id": str(seller.id),
        "shop_name": seller.shop_name,
        "commission_rate": str(seller.commission_rate),
        "image_url": public_url(images[0].thumb_key) if images else None,
        "attributes": [
            {"code": value.attribute.code, "name": value.attribute.name, "value": value.value}
            for value in variant.attribute_values.all()
        ],
    }


class VariantsBulkView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        body = BulkRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        ready_images = Prefetch(
            "product__images",
            queryset=ProductImage.objects.filter(status=ImageStatus.READY).order_by(
                "position", "created_at"
            ),
            to_attr="ready_images",
        )
        variants = (
            ProductVariant.objects.filter(id__in=body.validated_data["variant_ids"])
            .select_related("product__seller")
            .prefetch_related("attribute_values__attribute", ready_images)
            .order_by("id")
        )
        return Response({"items": [variant_info(variant) for variant in variants]})


# --- search documents -------------------------------------------------------------------


class SearchDocumentsQuerySerializer(serializers.Serializer[Any]):
    page = serializers.IntegerField(min_value=1, max_value=1_000_000, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=MAX_DOCUMENTS_PAGE, default=DEFAULT_DOCUMENTS_PAGE
    )


class SearchDocumentsView(APIView):
    """Every active product as its ``product.updated`` payload, for a full reindex."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        query = SearchDocumentsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page: int = query.validated_data["page"]
        page_size: int = query.validated_data["page_size"]

        products = Product.objects.filter(status=ProductStatus.ACTIVE.value).order_by("id")
        offset = (page - 1) * page_size
        batch = list(products.select_related("seller")[offset : offset + page_size])
        return Response(
            {
                "items": [
                    document.model_dump(mode="json") for document in build_product_documents(batch)
                ],
                "total": products.count(),
                "page": page,
                "page_size": page_size,
            }
        )


urlpatterns = [
    path("variants/bulk/", VariantsBulkView.as_view(), name="internal-variants-bulk"),
    path("search-documents/", SearchDocumentsView.as_view(), name="internal-search-documents"),
]
