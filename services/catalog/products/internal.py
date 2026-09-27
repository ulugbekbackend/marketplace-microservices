"""Service-to-service API (cart, order). Traefik routes only ``/api/catalog``, so
``/internal/catalog`` is reachable on the internal network only.

    POST /internal/catalog/variants/bulk/                   {variant_ids} -> {items}
    POST /internal/catalog/reservations/                    {order_id, items} -> reservation
    POST /internal/catalog/reservations/{order_id}/commit/  order paid
    POST /internal/catalog/reservations/{order_id}/release/ order expired or cancelled
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
from products import reservations
from products.models import ImageStatus, ProductImage, ProductVariant
from products.storage import public_url
from py_common.web.drf import ApiError

MAX_BULK = 200


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


# --- reservations -----------------------------------------------------------------------


class ReserveItemSerializer(serializers.Serializer[Any]):
    variant_id = serializers.UUIDField()
    qty = serializers.IntegerField(min_value=1, max_value=10_000)


class ReserveRequestSerializer(serializers.Serializer[Any]):
    order_id = serializers.UUIDField()
    items = serializers.ListField(
        child=ReserveItemSerializer(), allow_empty=False, max_length=MAX_BULK
    )


def reservation_body(result: reservations.Reserved) -> dict[str, Any]:
    return {
        "order_id": str(result.order_id),
        "status": result.status,
        "expires_at": result.expires_at.isoformat(),
        "items": _items(result.items),
    }


def _items(items: list[reservations.ReservationItem]) -> list[dict[str, Any]]:
    return [{"variant_id": str(item.variant_id), "qty": item.qty} for item in items]


class ReserveView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        body = ReserveRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        items = [
            reservations.ReservationItem(item["variant_id"], item["qty"])
            for item in body.validated_data["items"]
        ]
        result = reservations.reserve(body.validated_data["order_id"], items)
        if isinstance(result, reservations.ReserveFailed):
            raise ApiError(
                result.reason,
                "Some items are not available in the requested quantity.",
                status=409,
                details={"variant_ids": [str(variant_id) for variant_id in result.variant_ids]},
            )
        return Response(reservation_body(result))


class CommitView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(exclude=True)
    def post(self, request: Request, order_id: Any) -> Response:
        try:
            items = reservations.commit(order_id)
        except reservations.NotReserved as exc:
            raise ApiError(
                "NOT_RESERVED",
                "The order holds no stock to commit.",
                status=409,
                details={"order_id": str(order_id)},
            ) from exc
        return Response({"order_id": str(order_id), "status": "committed", "items": _items(items)})


class ReleaseView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(exclude=True)
    def post(self, request: Request, order_id: Any) -> Response:
        items = reservations.release(order_id)
        return Response({"order_id": str(order_id), "status": "released", "items": _items(items)})


urlpatterns = [
    path("variants/bulk/", VariantsBulkView.as_view(), name="internal-variants-bulk"),
    path("reservations/", ReserveView.as_view(), name="internal-reserve"),
    path(
        "reservations/<uuid:order_id>/commit/",
        CommitView.as_view(),
        name="internal-reservation-commit",
    ),
    path(
        "reservations/<uuid:order_id>/release/",
        ReleaseView.as_view(),
        name="internal-reservation-release",
    ),
]
