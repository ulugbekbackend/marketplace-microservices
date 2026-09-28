"""Seller fulfilment: sub-order status changes and the order roll-up they cause.

Every change locks the parent order first, then the sub-order (the same order the payment
code takes locks in), checks the state table, writes history and outbox rows and rolls
the order up, all in one transaction.
"""

from uuid import UUID

from django.db import transaction

from contracts.enums import OrderStatus, SubOrderStatus
from contracts.events import OrderRefundRequested, SubOrderStatusChanged
from orders.models import Order, SubOrder
from orders.services import publish
from orders.state import lock_order, lock_sub_order, transition, transition_sub_order
from py_common.web.drf import ApiError

# Order history reasons of the roll-up.
SUB_ORDER_SHIPPED = "SUB_ORDER_SHIPPED"
ALL_SUB_ORDERS_DELIVERED = "ALL_SUB_ORDERS_DELIVERED"

# The refund reason of a sub-order the seller cancelled.
CANCELLED_BY_SELLER = SubOrderStatus.CANCELLED_BY_SELLER.value

#: Order states in which sellers may still work on their sub-orders.
ACTIVE_ORDER_STATES = frozenset({OrderStatus.PAID.value, OrderStatus.FULFILLING.value})


class SubOrderNotFound(ApiError):
    """No such sub-order of this seller. Reaches the API as 404."""

    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "Sub-order not found.", status=404)


class OrderNotActive(ApiError):
    """The parent order is no longer being fulfilled. Reaches the API as 409."""

    def __init__(self, order_status: str) -> None:
        super().__init__(
            "ORDER_NOT_ACTIVE",
            f"The order is {order_status}; its sub-orders can no longer change.",
            status=409,
            details={"order_status": order_status},
        )


def change_status(
    seller_id: UUID,
    sub_order_id: UUID,
    target: SubOrderStatus,
    *,
    tracking_number: str = "",
    reason: str = "",
) -> SubOrder:
    """Move one of the seller's sub-orders to ``target`` and roll the order up.

    Raises SubOrderNotFound for unknown or foreign sub-orders, OrderNotActive when the
    order is not PAID/FULFILLING and InvalidTransition for a disallowed change.
    """
    order_id = (
        SubOrder.objects.filter(id=sub_order_id, seller_id=seller_id)
        .values_list("order_id", flat=True)
        .first()
    )
    if order_id is None:
        raise SubOrderNotFound

    with transaction.atomic():
        order = lock_order(order_id)
        sub_order = lock_sub_order(sub_order_id)
        if order.status not in ACTIVE_ORDER_STATES:
            raise OrderNotActive(order.status)
        transition_sub_order(sub_order, target, reason=reason, tracking_number=tracking_number)
        publish(
            order,
            SubOrderStatusChanged(
                sub_order_id=sub_order.id,
                order_id=order.id,
                seller_id=sub_order.seller_id,
                customer_id=order.customer_id,
                status=target,
            ),
        )
        if target is SubOrderStatus.CANCELLED_BY_SELLER:
            # The commission was never earned: the customer gets the whole subtotal back.
            publish(
                order,
                OrderRefundRequested(
                    order_id=order.id,
                    amount_tiyin=sub_order.subtotal_tiyin,
                    reason=CANCELLED_BY_SELLER,
                ),
            )
        roll_up(order)
    return sub_order


def roll_up(order: Order) -> None:
    """Derive the locked order's status from its sub-orders.

    The first shipped sub-order moves PAID -> FULFILLING. Once every sub-order that was
    not cancelled is delivered (and at least one is), FULFILLING -> COMPLETED. If every
    sub-order is cancelled the order stays PAID until the refund arrives.
    """
    statuses = set(order.sub_orders.values_list("status", flat=True))
    live = statuses - {SubOrderStatus.CANCELLED_BY_SELLER.value}
    progressed = live & {SubOrderStatus.SHIPPED.value, SubOrderStatus.DELIVERED.value}
    if order.status == OrderStatus.PAID.value and progressed:
        transition(order, OrderStatus.FULFILLING, reason=SUB_ORDER_SHIPPED)
    if order.status == OrderStatus.FULFILLING.value and live == {SubOrderStatus.DELIVERED.value}:
        transition(order, OrderStatus.COMPLETED, reason=ALL_SUB_ORDERS_DELIVERED)
