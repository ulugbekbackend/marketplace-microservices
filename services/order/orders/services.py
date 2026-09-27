"""Order use cases: checkout, reservation, payment, cancellation and expiry.

In P2 the API calls these synchronously; in P4 the event consumers call the same
functions (``reserve_stock`` on order creation, ``mark_paid`` on ``payment.paid``,
``expire_overdue`` from a scheduled task). Every status change locks the order row,
goes through ``state.transition`` and writes its outbox event in the same transaction.
HTTP calls to other services never run while a row lock is held.
"""

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from contracts.enums import OrderStatus
from contracts.events import (
    Frozen,
    OrderCancelled,
    OrderCreated,
    OrderExpired,
    OrderItemRef,
    OrderPaid,
    SubOrderRef,
    build_event,
)
from contracts.money import apply_commission
from messaging.outbox import PRODUCER, add_to_outbox
from orders import clients
from orders.clients import CartLine, NotReserved, ReserveRejected, ServiceUnavailable, VariantInfo
from orders.models import Order, OrderItem, SubOrder
from orders.state import InvalidTransition, can_transition, lock_order, record_created, transition
from py_common.web.drf import ApiError

logger = logging.getLogger(__name__)

# cancel_reason values
OUT_OF_STOCK = "OUT_OF_STOCK"
RESERVATION_FAILED = "RESERVATION_FAILED"
CANCELLED_BY_CUSTOMER = "CANCELLED_BY_CUSTOMER"
RESERVATION_EXPIRED = "RESERVATION_EXPIRED"

PAID_STATES = frozenset({OrderStatus.PAID, OrderStatus.FULFILLING, OrderStatus.COMPLETED})


# --- checkout -----------------------------------------------------------------------


def checkout(customer_id: UUID, address: dict[str, Any]) -> Order:
    """Turn the customer's cart into an order and try to hold its stock.

    Returns the order as RESERVED, or CANCELLED when the stock could not be held.
    Raises CART_EMPTY / ITEMS_UNAVAILABLE (nothing written) or SERVICE_UNAVAILABLE.
    """
    wanted = merge_lines(clients.get_cart(customer_id))
    if not wanted:
        raise ApiError("CART_EMPTY", "The cart is empty.", status=409)

    variants = clients.variants_bulk(wanted)
    problems = unavailable_items(wanted, variants)
    if problems:
        raise ApiError(
            "ITEMS_UNAVAILABLE",
            "Some items are no longer available in the requested quantity.",
            status=409,
            details={"items": problems},
        )

    order = create_order(customer_id, address, wanted, variants)
    return reserve_stock(order.id)


def merge_lines(lines: Iterable[CartLine]) -> dict[UUID, int]:
    """Quantities per variant, in cart order; repeated variants are summed."""
    wanted: dict[UUID, int] = {}
    for line in lines:
        if line.qty > 0:
            wanted[line.variant_id] = wanted.get(line.variant_id, 0) + line.qty
    return wanted


def unavailable_items(
    wanted: dict[UUID, int], variants: dict[UUID, VariantInfo]
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for variant_id, qty in wanted.items():
        info = variants.get(variant_id)
        if info is None:
            problems.append({"variant_id": str(variant_id), "reason": "not_found", "available": 0})
        elif not info.is_active:
            problems.append(
                {"variant_id": str(variant_id), "reason": "inactive", "available": info.available}
            )
        elif info.available < qty:
            problems.append(
                {
                    "variant_id": str(variant_id),
                    "reason": "out_of_stock",
                    "available": info.available,
                }
            )
    return problems


def create_order(
    customer_id: UUID,
    address: dict[str, Any],
    wanted: dict[UUID, int],
    variants: dict[UUID, VariantInfo],
) -> Order:
    """PENDING order with price snapshots, its history row and ``order.created``."""
    with transaction.atomic():
        order = Order.objects.create(
            customer_id=customer_id,
            status=OrderStatus.PENDING.value,
            total_tiyin=sum(variants[vid].price_tiyin * qty for vid, qty in wanted.items()),
            delivery_address=address,
        )
        OrderItem.objects.bulk_create(
            [_snapshot(order, variants[variant_id], qty) for variant_id, qty in wanted.items()]
        )
        record_created(order)
        _publish(
            order,
            OrderCreated(
                order_id=order.id,
                items=[OrderItemRef(variant_id=vid, qty=qty) for vid, qty in wanted.items()],
            ),
        )
    return order


def _snapshot(order: Order, info: VariantInfo, qty: int) -> OrderItem:
    return OrderItem(
        order=order,
        variant_id=info.variant_id,
        seller_id=info.seller_id,
        shop_name_snapshot=info.shop_name,
        title_snapshot=info.title,
        sku_snapshot=info.sku,
        image_snapshot=info.image_url or "",
        price_snapshot_tiyin=info.price_tiyin,
        qty=qty,
    )


# --- reservation ----------------------------------------------------------------------


def reserve_stock(order_id: UUID) -> Order:
    """Ask the catalog to hold the order's stock: PENDING -> RESERVED or CANCELLED."""
    items = _item_refs(order_id)
    try:
        result = clients.reserve(order_id, [(ref.variant_id, ref.qty) for ref in items])
    except ServiceUnavailable:
        logger.warning("reservation failed, releasing", extra={"order_id": str(order_id)})
        _release_quietly(order_id)
        return _cancel_pending(order_id, RESERVATION_FAILED)

    if isinstance(result, ReserveRejected):
        reason = OUT_OF_STOCK if result.code == OUT_OF_STOCK else RESERVATION_FAILED
        return _cancel_pending(order_id, reason)

    with transaction.atomic():
        order = lock_order(order_id)
        if order.status == OrderStatus.PENDING.value:
            order.reserved_until = result.expires_at
            order.save(update_fields=["reserved_until", "updated_at"])
            return transition(order, OrderStatus.RESERVED)
    # Cancelled while the catalog was reserving: the stock it just took goes back.
    _release_quietly(order_id)
    return order


def _cancel_pending(order_id: UUID, reason: str) -> Order:
    with transaction.atomic():
        order = lock_order(order_id)
        if order.status == OrderStatus.PENDING.value:
            _cancel_locked(order, reason)
        return order


# --- payment --------------------------------------------------------------------------


def mark_paid(order_id: UUID, *, allow_expired: bool = False) -> Order:
    """The order is paid: commit its stock, split it per seller, publish ``order.paid``.

    Idempotent: an order that is already paid is returned unchanged. The mock payment
    endpoint calls this now; the ``payment.paid`` consumer (P5) calls it with
    ``allow_expired=True`` for late payments.
    """
    order = Order.objects.get(id=order_id)
    if order.status in PAID_STATES:
        return order
    if not allow_expired and (expire_if_overdue(order) or order.status == OrderStatus.EXPIRED):
        raise ApiError(
            "ORDER_EXPIRED",
            "The reservation of this order has expired.",
            status=409,
            details={"order_id": str(order_id)},
        )
    if not can_transition(OrderStatus(order.status), OrderStatus.PAID):
        raise InvalidTransition(order.status, OrderStatus.PAID.value)

    items = list(order.items.all())
    # Read the rates before committing: if the catalog is down, the stock stays held.
    rates = _commission_rates(items)
    try:
        clients.commit(order_id)
    except NotReserved as exc:
        raise ApiError(
            "NOT_RESERVED",
            "The catalog holds no stock for this order.",
            status=409,
            details={"order_id": str(order_id)},
        ) from exc

    with transaction.atomic():
        order = lock_order(order_id)
        if order.status in PAID_STATES:
            return order  # a concurrent call got here first
        transition(order, OrderStatus.PAID)
        sub_orders = _split_by_seller(order, items, rates)
        _publish(
            order,
            OrderPaid(
                order_id=order.id,
                customer_id=order.customer_id,
                sub_orders=[
                    SubOrderRef(
                        id=sub_order.id,
                        seller_id=sub_order.seller_id,
                        items=[
                            OrderItemRef(variant_id=item.variant_id, qty=item.qty) for item in lines
                        ],
                        subtotal_tiyin=sub_order.subtotal_tiyin,
                        commission_tiyin=sub_order.commission_tiyin,
                    )
                    for sub_order, lines in sub_orders
                ],
            ),
        )

    _clear_cart_quietly(order.customer_id)
    return order


def _commission_rates(items: list[OrderItem]) -> dict[UUID, Decimal]:
    """Each seller's current commission rate, read fresh from the catalog."""
    variants = clients.variants_bulk(item.variant_id for item in items)
    rates = {info.seller_id: info.commission_rate for info in variants.values()}
    missing = {item.seller_id for item in items} - rates.keys()
    if missing:
        logger.error(
            "commission rate unknown", extra={"seller_ids": sorted(str(s) for s in missing)}
        )
        raise ServiceUnavailable(clients.CATALOG)
    return rates


def _split_by_seller(
    order: Order, items: list[OrderItem], rates: dict[UUID, Decimal]
) -> list[tuple[SubOrder, list[OrderItem]]]:
    by_seller: dict[UUID, list[OrderItem]] = defaultdict(list)
    for item in items:
        by_seller[item.seller_id].append(item)

    result: list[tuple[SubOrder, list[OrderItem]]] = []
    for seller_id in sorted(by_seller):
        lines = by_seller[seller_id]
        subtotal = sum(item.line_total_tiyin for item in lines)
        rate = rates[seller_id]
        sub_order = SubOrder.objects.create(
            order=order,
            seller_id=seller_id,
            subtotal_tiyin=subtotal,
            commission_rate_snapshot=rate,
            commission_tiyin=apply_commission(subtotal, rate),
        )
        OrderItem.objects.filter(id__in=[item.id for item in lines]).update(sub_order=sub_order)
        result.append((sub_order, lines))
    return result


# --- cancellation and expiry --------------------------------------------------------------


def cancel_order(order_id: UUID, *, reason: str = CANCELLED_BY_CUSTOMER) -> Order:
    """PENDING or RESERVED -> CANCELLED, then the held stock is released."""
    with transaction.atomic():
        order = lock_order(order_id)
        _cancel_locked(order, reason)
    _release_quietly(order_id)
    return order


def expire_order(order_id: UUID, *, now: datetime | None = None) -> bool:
    """RESERVED past ``reserved_until`` -> EXPIRED and release. False when not overdue."""
    with transaction.atomic():
        order = lock_order(order_id)
        if not is_overdue(order, now):
            return False
        _expire_locked(order)
    _release_quietly(order_id)
    return True


def expire_if_overdue(order: Order) -> bool:
    """Lazy expiry on read: expire the order if it is overdue and refresh it."""
    if not is_overdue(order):
        return False
    expired = expire_order(order.id)
    order.refresh_from_db()
    return expired


def expire_overdue(*, batch_size: int = 100, now: datetime | None = None) -> int:
    """Expire every overdue order. Rows locked by another worker are skipped."""
    total = 0
    while True:
        moment = now or timezone.now()
        with transaction.atomic():
            batch = list(
                Order.objects.select_for_update(skip_locked=True)
                .filter(status=OrderStatus.RESERVED.value, reserved_until__lt=moment)
                .order_by("reserved_until", "id")[:batch_size]
            )
            for order in batch:
                _expire_locked(order)
        for order in batch:
            _release_quietly(order.id)
        total += len(batch)
        if len(batch) < batch_size:
            return total


def is_overdue(order: Order, now: datetime | None = None) -> bool:
    return (
        order.status == OrderStatus.RESERVED.value
        and order.reserved_until is not None
        and order.reserved_until < (now or timezone.now())
    )


def _expire_locked(order: Order) -> None:
    transition(order, OrderStatus.EXPIRED, reason=RESERVATION_EXPIRED)
    _publish(order, OrderExpired(order_id=order.id, items=_item_refs(order.id)))


def _cancel_locked(order: Order, reason: str) -> None:
    transition(order, OrderStatus.CANCELLED, reason=reason)
    _publish(order, OrderCancelled(order_id=order.id, items=_item_refs(order.id), reason=reason))


# --- helpers ----------------------------------------------------------------------------


def _item_refs(order_id: UUID) -> list[OrderItemRef]:
    return [
        OrderItemRef(variant_id=variant_id, qty=qty)
        for variant_id, qty in OrderItem.objects.filter(order_id=order_id)
        .order_by("variant_id")
        .values_list("variant_id", "qty")
    ]


def _publish(order: Order, payload: Frozen) -> None:
    add_to_outbox(
        build_event(payload, producer=PRODUCER, correlation_id=order.id, occurred_at=timezone.now())
    )


def _release_quietly(order_id: UUID) -> None:
    """Best effort: in P4 the ``order.cancelled``/``order.expired`` events release too."""
    try:
        clients.release(order_id)
    except ServiceUnavailable:
        logger.warning("stock release failed", extra={"order_id": str(order_id)})


def _clear_cart_quietly(customer_id: UUID) -> None:
    try:
        clients.clear_cart(customer_id)
    except ServiceUnavailable:
        logger.warning("cart clear failed", extra={"customer_id": str(customer_id)})
