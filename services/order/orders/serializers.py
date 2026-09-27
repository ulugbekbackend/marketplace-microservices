"""Request validation and response shapes of the order API."""

from collections import defaultdict
from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from orders.models import (
    ORDER_STATUS_CHOICES,
    SUB_ORDER_STATUS_CHOICES,
    Order,
    OrderItem,
    OrderStatusHistory,
    SubOrder,
)

PHONE_PATTERN = r"^\+?[0-9][0-9 ()-]{6,19}$"

# --- requests ---------------------------------------------------------------------------


class AddressSerializer(serializers.Serializer[dict[str, Any]]):
    full_name = serializers.CharField(max_length=120)
    phone = serializers.RegexField(
        PHONE_PATTERN,
        max_length=20,
        error_messages={"invalid": "Enter a valid phone number, e.g. +998901234567."},
    )
    region = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100)
    street = serializers.CharField(max_length=255)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class CheckoutSerializer(serializers.Serializer[dict[str, Any]]):
    address = AddressSerializer()


# --- responses --------------------------------------------------------------------------


class CheckoutResultSerializer(serializers.Serializer[dict[str, Any]]):
    order_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=ORDER_STATUS_CHOICES)


class OrderStatusSerializer(serializers.ModelSerializer[Order]):
    class Meta:
        model = Order
        fields = ("status", "reserved_until")
        read_only_fields = fields


class OrderSummarySerializer(serializers.ModelSerializer[Order]):
    items_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = ("id", "status", "total_tiyin", "items_count", "reserved_until", "created_at")
        read_only_fields = fields


class OrderItemSerializer(serializers.ModelSerializer[OrderItem]):
    title = serializers.CharField(source="title_snapshot")
    sku = serializers.CharField(source="sku_snapshot")
    image_url = serializers.SerializerMethodField()
    price_tiyin = serializers.IntegerField(source="price_snapshot_tiyin")
    line_total_tiyin = serializers.IntegerField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "variant_id",
            "title",
            "sku",
            "image_url",
            "price_tiyin",
            "qty",
            "line_total_tiyin",
        )
        read_only_fields = fields

    def get_image_url(self, item: OrderItem) -> str | None:
        return item.image_snapshot or None


class OrderHistorySerializer(serializers.ModelSerializer[OrderStatusHistory]):
    from_status = serializers.ChoiceField(choices=ORDER_STATUS_CHOICES, allow_null=True)
    to_status = serializers.ChoiceField(choices=ORDER_STATUS_CHOICES)

    class Meta:
        model = OrderStatusHistory
        fields = ("from_status", "to_status", "reason", "created_at")
        read_only_fields = fields


class SellerGroupSerializer(serializers.Serializer[dict[str, Any]]):
    """The items of one seller. ``sub_order_id``/``status`` stay null until payment."""

    seller_id = serializers.UUIDField()
    shop_name = serializers.CharField()
    sub_order_id = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(choices=SUB_ORDER_STATUS_CHOICES, allow_null=True)
    subtotal_tiyin = serializers.IntegerField()
    items = OrderItemSerializer(many=True)


class OrderDetailSerializer(serializers.ModelSerializer[Order]):
    delivery_address = AddressSerializer()
    sellers = serializers.SerializerMethodField()
    history = OrderHistorySerializer(many=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "total_tiyin",
            "delivery_address",
            "reserved_until",
            "cancel_reason",
            "created_at",
            "updated_at",
            "sellers",
            "history",
        )
        read_only_fields = fields

    @extend_schema_field(SellerGroupSerializer(many=True))
    def get_sellers(self, order: Order) -> Any:
        return [SellerGroupSerializer(group).data for group in seller_groups(order)]


def seller_groups(order: Order) -> list[dict[str, Any]]:
    """Items grouped per seller, with the seller's sub-order once the order is paid."""
    sub_orders: dict[UUID, SubOrder] = {sub.seller_id: sub for sub in order.sub_orders.all()}
    items: dict[UUID, list[OrderItem]] = defaultdict(list)
    for item in order.items.all():
        items[item.seller_id].append(item)

    groups = []
    for seller_id, lines in items.items():
        sub_order = sub_orders.get(seller_id)
        groups.append(
            {
                "seller_id": seller_id,
                "shop_name": lines[0].shop_name_snapshot,
                "sub_order_id": sub_order.id if sub_order else None,
                "status": sub_order.status if sub_order else None,
                "subtotal_tiyin": sum(line.line_total_tiyin for line in lines),
                "items": lines,
            }
        )
    return groups


# --- error shape (OpenAPI only) -----------------------------------------------------------


class ErrorBodySerializer(serializers.Serializer[dict[str, Any]]):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField()


class ErrorSerializer(serializers.Serializer[dict[str, Any]]):
    error = ErrorBodySerializer()
