"""Orders: one order per checkout, split into one sub-order per seller once it is paid."""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from contracts.enums import OrderStatus, SubOrderStatus
from contracts.ids import uuid7

ORDER_STATUS_CHOICES = [(status.value, status.name.title()) for status in OrderStatus]
SUB_ORDER_STATUS_CHOICES = [(status.value, status.name.title()) for status in SubOrderStatus]


class Order(models.Model):
    """A customer's purchase. Prices are snapshots taken at checkout, never re-read."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    customer_id = models.UUIDField()
    status = models.CharField(
        max_length=16, choices=ORDER_STATUS_CHOICES, default=OrderStatus.PENDING.value
    )
    total_tiyin = models.BigIntegerField()
    delivery_address = models.JSONField()
    # Until when the catalog holds the stock; set once the order is RESERVED.
    reserved_until = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = (
            models.Index(fields=["customer_id", "-created_at"], name="order_customer_created_idx"),
            models.Index(
                fields=["reserved_until"],
                condition=Q(status=OrderStatus.RESERVED.value),
                name="order_reserved_until_idx",
            ),
        )
        constraints = (
            models.CheckConstraint(
                condition=Q(total_tiyin__gte=0), name="order_total_non_negative"
            ),
        )

    def __str__(self) -> str:
        return f"{self.id} {self.status}"


class SubOrder(models.Model):
    """The part of a paid order one seller fulfils. Commission is fixed at payment time."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="sub_orders")
    seller_id = models.UUIDField()
    status = models.CharField(
        max_length=24, choices=SUB_ORDER_STATUS_CHOICES, default=SubOrderStatus.NEW.value
    )
    subtotal_tiyin = models.BigIntegerField()
    commission_rate_snapshot = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0")
    )
    commission_tiyin = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = (models.Index(fields=["seller_id", "-created_at"], name="suborder_seller_idx"),)
        constraints = (
            models.UniqueConstraint(fields=["order", "seller_id"], name="suborder_order_seller"),
            models.CheckConstraint(
                condition=Q(subtotal_tiyin__gte=0, commission_tiyin__gte=0),
                name="suborder_amounts_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(commission_rate_snapshot__gte=0, commission_rate_snapshot__lte=1),
                name="suborder_commission_rate_range",
            ),
        )

    def __str__(self) -> str:
        return f"{self.id} {self.status}"


class OrderItem(models.Model):
    """One order line with everything the customer saw at checkout."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sub_order = models.ForeignKey(
        SubOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    variant_id = models.UUIDField()
    seller_id = models.UUIDField()
    shop_name_snapshot = models.CharField(max_length=120, blank=True, default="")
    title_snapshot = models.CharField(max_length=200)
    sku_snapshot = models.CharField(max_length=64)
    image_snapshot = models.CharField(max_length=500, blank=True, default="")
    price_snapshot_tiyin = models.BigIntegerField()
    qty = models.PositiveIntegerField()

    class Meta:
        ordering = ("seller_id", "title_snapshot", "id")
        constraints = (
            models.UniqueConstraint(fields=["order", "variant_id"], name="orderitem_order_variant"),
            models.CheckConstraint(
                condition=Q(price_snapshot_tiyin__gt=0), name="orderitem_price_positive"
            ),
            models.CheckConstraint(condition=Q(qty__gt=0), name="orderitem_qty_positive"),
        )

    def __str__(self) -> str:
        return f"{self.sku_snapshot} x{self.qty}"

    @property
    def line_total_tiyin(self) -> int:
        return self.price_snapshot_tiyin * self.qty


class OrderStatusHistory(models.Model):
    """Every order status change, oldest first. ``from_status`` is empty for creation."""

    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(
        max_length=16, choices=ORDER_STATUS_CHOICES, null=True, blank=True
    )
    to_status = models.CharField(max_length=16, choices=ORDER_STATUS_CHOICES)
    reason = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name_plural = "order status history"

    def __str__(self) -> str:
        return f"{self.from_status} -> {self.to_status}"
