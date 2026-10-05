"""Request validation and response shapes of the order API."""

from collections import defaultdict
from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from contracts.enums import SubOrderStatus
from orders.models import (
    ORDER_STATUS_CHOICES,
    SUB_ORDER_STATUS_CHOICES,
    Order,
    OrderItem,
    OrderStatusHistory,
    SubOrder,
    SubOrderStatusHistory,
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


class SubOrderHistorySerializer(serializers.ModelSerializer[SubOrderStatusHistory]):
    from_status = serializers.ChoiceField(choices=SUB_ORDER_STATUS_CHOICES, allow_null=True)
    to_status = serializers.ChoiceField(choices=SUB_ORDER_STATUS_CHOICES)

    class Meta:
        model = SubOrderStatusHistory
        fields = ("from_status", "to_status", "reason", "created_at")
        read_only_fields = fields


class SellerGroupSerializer(serializers.Serializer[dict[str, Any]]):
    """The items of one seller. Sub-order fields stay null (history empty) until payment."""

    seller_id = serializers.UUIDField()
    shop_name = serializers.CharField()
    sub_order_id = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(choices=SUB_ORDER_STATUS_CHOICES, allow_null=True)
    tracking_number = serializers.CharField(allow_null=True)
    cancel_reason = serializers.CharField(allow_null=True)
    subtotal_tiyin = serializers.IntegerField()
    items = OrderItemSerializer(many=True)
    history = SubOrderHistorySerializer(many=True)


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
            "late_payment",
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
                "tracking_number": sub_order.tracking_number if sub_order else None,
                "cancel_reason": sub_order.cancel_reason if sub_order else None,
                "subtotal_tiyin": sum(line.line_total_tiyin for line in lines),
                "items": lines,
                "history": sub_order.history.all() if sub_order else [],
            }
        )
    return groups


# --- seller ---------------------------------------------------------------------------

#: Statuses a seller may move a sub-order to (NEW is only ever the starting point).
SELLER_TARGETS = [
    (status.value, status.name.title())
    for status in SubOrderStatus
    if status is not SubOrderStatus.NEW
]


class SellerListFilterSerializer(serializers.Serializer[dict[str, Any]]):
    """Query parameters of the seller list; dates are Tashkent calendar days, inclusive."""

    status = serializers.ListField(
        child=serializers.ChoiceField(choices=SUB_ORDER_STATUS_CHOICES), required=False
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start, end = attrs.get("date_from"), attrs.get("date_to")
        if start and end and start > end:
            raise serializers.ValidationError({"date_to": ["Must not be before date_from."]})
        return attrs


class SubOrderStatusChangeSerializer(serializers.Serializer[dict[str, Any]]):
    """SHIPPED needs a tracking number, CANCELLED_BY_SELLER a reason."""

    status = serializers.ChoiceField(choices=SELLER_TARGETS)
    tracking_number = serializers.CharField(max_length=64, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        target = SubOrderStatus(attrs["status"])
        attrs["tracking_number"] = attrs.get("tracking_number", "").strip()
        attrs["reason"] = attrs.get("reason", "").strip()
        if target is SubOrderStatus.SHIPPED and not attrs["tracking_number"]:
            raise serializers.ValidationError(
                {"tracking_number": ["A tracking number is required to ship."]}
            )
        if target is SubOrderStatus.CANCELLED_BY_SELLER and not attrs["reason"]:
            raise serializers.ValidationError({"reason": ["A reason is required to cancel."]})
        return attrs


class SellerSubOrderSerializer(serializers.ModelSerializer[SubOrder]):
    """A row of the seller list. Needs ``items_count`` annotated and ``order`` joined."""

    status = serializers.ChoiceField(choices=SUB_ORDER_STATUS_CHOICES)
    net_tiyin = serializers.IntegerField(read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    customer_name = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()

    class Meta:
        model = SubOrder
        fields: tuple[str, ...] = (
            "id",
            "order_id",
            "status",
            "subtotal_tiyin",
            "commission_tiyin",
            "net_tiyin",
            "items_count",
            "created_at",
            "updated_at",
            "customer_name",
            "city",
        )
        read_only_fields = fields

    def get_customer_name(self, sub_order: SubOrder) -> str:
        return str(sub_order.order.delivery_address.get("full_name", ""))

    def get_city(self, sub_order: SubOrder) -> str:
        return str(sub_order.order.delivery_address.get("city", ""))


class SellerItemSerializer(serializers.ModelSerializer[OrderItem]):
    title = serializers.CharField(source="title_snapshot")
    sku = serializers.CharField(source="sku_snapshot")
    image = serializers.SerializerMethodField()
    price_tiyin = serializers.IntegerField(source="price_snapshot_tiyin")
    line_total_tiyin = serializers.IntegerField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "variant_id",
            "title",
            "sku",
            "image",
            "price_tiyin",
            "qty",
            "line_total_tiyin",
        )
        read_only_fields = fields

    def get_image(self, item: OrderItem) -> str | None:
        return item.image_snapshot or None


class SellerSubOrderDetailSerializer(SellerSubOrderSerializer):
    """One sub-order with everything needed to ship it, including the customer's phone."""

    commission_rate = serializers.DecimalField(
        source="commission_rate_snapshot", max_digits=5, decimal_places=4
    )
    items = SellerItemSerializer(many=True)
    delivery_address = AddressSerializer(source="order.delivery_address")
    order_status = serializers.ChoiceField(source="order.status", choices=ORDER_STATUS_CHOICES)
    history = SubOrderHistorySerializer(many=True)

    class Meta(SellerSubOrderSerializer.Meta):
        fields = (
            *SellerSubOrderSerializer.Meta.fields,
            "commission_rate",
            "tracking_number",
            "cancel_reason",
            "items",
            "delivery_address",
            "order_status",
            "history",
        )
        read_only_fields = fields


class PeriodStatsSerializer(serializers.Serializer[dict[str, Any]]):
    orders = serializers.IntegerField()
    gross_tiyin = serializers.IntegerField()
    net_tiyin = serializers.IntegerField()


class DailyStatsSerializer(PeriodStatsSerializer):
    date = serializers.DateField()


class StatusCountsSerializer(serializers.Serializer[dict[str, Any]]):
    NEW = serializers.IntegerField()
    ACCEPTED = serializers.IntegerField()
    SHIPPED = serializers.IntegerField()
    DELIVERED = serializers.IntegerField()
    CANCELLED_BY_SELLER = serializers.IntegerField()


class SellerStatsSerializer(serializers.Serializer[dict[str, Any]]):
    """Tashkent today / ISO week / calendar month, the last 30 days and per-status counts."""

    today = PeriodStatsSerializer()
    week = PeriodStatsSerializer()
    month = PeriodStatsSerializer()
    daily = DailyStatsSerializer(many=True)
    by_status = StatusCountsSerializer()


# --- error shape (OpenAPI only) -----------------------------------------------------------


class ErrorBodySerializer(serializers.Serializer[dict[str, Any]]):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField()


class ErrorSerializer(serializers.Serializer[dict[str, Any]]):
    error = ErrorBodySerializer()
