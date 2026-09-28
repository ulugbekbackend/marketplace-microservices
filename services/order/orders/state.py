"""Order and sub-order state machines: an allowed-transitions table and one guarded setter.

Callers lock the rows first (``lock_order``, then ``lock_sub_order``) inside
``transaction.atomic``; the transition functions check the table, save the new status and
record the change in the history table.
"""

from uuid import UUID

from django.db import transaction

from contracts.enums import OrderStatus, SubOrderStatus
from orders.models import Order, OrderStatusHistory, SubOrder, SubOrderStatusHistory
from py_common.web.drf import ApiError

ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.RESERVED, OrderStatus.CANCELLED}),
    OrderStatus.RESERVED: frozenset({OrderStatus.PAID, OrderStatus.EXPIRED, OrderStatus.CANCELLED}),
    OrderStatus.PAID: frozenset({OrderStatus.FULFILLING, OrderStatus.REFUNDED}),
    OrderStatus.FULFILLING: frozenset({OrderStatus.COMPLETED, OrderStatus.REFUNDED}),
    # A payment that arrives after expiry: taken (and stock re-reserved) or refunded.
    OrderStatus.EXPIRED: frozenset({OrderStatus.PAID, OrderStatus.REFUNDED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REFUNDED: frozenset(),
}

SUB_ORDER_TRANSITIONS: dict[SubOrderStatus, frozenset[SubOrderStatus]] = {
    SubOrderStatus.NEW: frozenset({SubOrderStatus.ACCEPTED, SubOrderStatus.CANCELLED_BY_SELLER}),
    SubOrderStatus.ACCEPTED: frozenset(
        {SubOrderStatus.SHIPPED, SubOrderStatus.CANCELLED_BY_SELLER}
    ),
    SubOrderStatus.SHIPPED: frozenset({SubOrderStatus.DELIVERED}),
    SubOrderStatus.DELIVERED: frozenset(),
    SubOrderStatus.CANCELLED_BY_SELLER: frozenset(),
}


class InvalidTransition(ApiError):
    """The requested status change is not in the table. Reaches the API as 409."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            "INVALID_TRANSITION",
            f"Cannot change status from {current} to {target}.",
            status=409,
            details={"from": current, "to": target},
        )
        self.current = current
        self.target = target


class NotInTransaction(RuntimeError):
    """Status changes must run inside transaction.atomic on a locked row."""


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ORDER_TRANSITIONS[current]


def can_transition_sub_order(current: SubOrderStatus, target: SubOrderStatus) -> bool:
    return target in SUB_ORDER_TRANSITIONS[current]


def lock_order(order_id: UUID) -> Order:
    """SELECT ... FOR UPDATE on one order. Raises Order.DoesNotExist."""
    _require_transaction()
    return Order.objects.select_for_update().get(id=order_id)


def transition(order: Order, target: OrderStatus, *, reason: str = "") -> Order:
    """Move a locked order to ``target`` and write a history row."""
    _require_transaction()
    current = OrderStatus(order.status)
    if not can_transition(current, target):
        raise InvalidTransition(current.value, target.value)
    order.status = target.value
    fields = ["status", "updated_at"]
    if target is OrderStatus.CANCELLED:
        order.cancel_reason = reason
        fields.append("cancel_reason")
    order.save(update_fields=fields)
    OrderStatusHistory.objects.create(
        order=order, from_status=current.value, to_status=target.value, reason=reason
    )
    return order


def record_created(order: Order) -> None:
    """The first history row of a new order."""
    OrderStatusHistory.objects.create(order=order, from_status=None, to_status=order.status)


def record_sub_order_created(sub_order: SubOrder) -> None:
    """The first history row of a new sub-order."""
    SubOrderStatusHistory.objects.create(
        sub_order=sub_order, from_status=None, to_status=sub_order.status
    )


def lock_sub_order(sub_order_id: UUID) -> SubOrder:
    """SELECT ... FOR UPDATE on one sub-order. Lock its order first (``lock_order``)."""
    _require_transaction()
    return SubOrder.objects.select_for_update().get(id=sub_order_id)


def transition_sub_order(
    sub_order: SubOrder,
    target: SubOrderStatus,
    *,
    reason: str = "",
    tracking_number: str = "",
) -> SubOrder:
    """Move a locked sub-order to ``target`` and write a history row.

    SHIPPED stores ``tracking_number``; CANCELLED_BY_SELLER stores ``reason`` as the
    cancel reason. Every change keeps ``reason`` in the history row.
    """
    _require_transaction()
    current = SubOrderStatus(sub_order.status)
    if not can_transition_sub_order(current, target):
        raise InvalidTransition(current.value, target.value)
    sub_order.status = target.value
    fields = ["status", "updated_at"]
    if target is SubOrderStatus.SHIPPED:
        sub_order.tracking_number = tracking_number
        fields.append("tracking_number")
    elif target is SubOrderStatus.CANCELLED_BY_SELLER:
        sub_order.cancel_reason = reason
        fields.append("cancel_reason")
    sub_order.save(update_fields=fields)
    SubOrderStatusHistory.objects.create(
        sub_order=sub_order, from_status=current.value, to_status=target.value, reason=reason
    )
    return sub_order


def _require_transaction() -> None:
    if not transaction.get_connection().in_atomic_block:
        raise NotInTransaction("status changes must run inside transaction.atomic")
