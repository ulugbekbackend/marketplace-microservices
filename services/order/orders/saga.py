"""The order side of the checkout saga: reactions to catalog and payment events.

Each handler runs in one transaction: it records the event id (a redelivery changes
nothing), locks the order, moves it through the state table and writes the outbox events
of the change. Commission rates are read over HTTP before the lock; the cart is cleared
after the commit.

    order.created  -> catalog -> stock.reserved   PENDING -> RESERVED
                              -> stock.failed     PENDING -> CANCELLED (OUT_OF_STOCK)
    payment.paid                                  RESERVED -> PAID (+ sub-orders, order.paid)
                                                  EXPIRED  -> late_payment, order.created again
    late payment: stock.reserved                  EXPIRED  -> PAID
                  stock.failed                    EXPIRED  -> REFUNDED (+ order.refund_requested)
    payment.refunded                              -> REFUNDED when the table allows it

Events that arrive in a state they no longer apply to are handled on purpose, never by
failing (which would only retry and dead letter them):

- ``stock.reserved`` for a CANCELLED order: the customer cancelled while the catalog was
  reserving. The catalog holds the stock now, and the ``order.cancelled`` published at
  cancel time may have reached it before ``order.created`` (a retried delivery), in which
  case it released nothing. ``order.cancelled`` is published again: it is published after
  the reservation exists and the catalog's release is idempotent, so the stock is freed
  either way. Consumers of ``order.cancelled`` see the order cancelled twice.
- ``stock.reserved`` for an EXPIRED order without a late payment, or for a late payment
  that was refunded meanwhile: ``order.expired`` is published again for the same reason.
- ``stock.reserved`` / ``stock.failed`` in any other state: logged and ignored.
- ``payment.paid`` for a PENDING order: the stock is not reserved yet, so the handler
  raises ``NotReserved`` and the consumer retries the message a little later.
- ``payment.paid`` for a CANCELLED order: the money cannot be used, so
  ``order.refund_requested`` is published; the order stays CANCELLED.
- ``payment.paid`` for a PAID (or later) or REFUNDED order: nothing (idempotent).
- ``payment.refunded`` that only covers part of a paid order (a seller cancelled one
  sub-order) or arrives in a state the table does not allow: logged and ignored.

An unknown order id or a malformed payload goes straight to the dead letter queue.
"""

import logging
from collections.abc import Mapping
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from contracts.enums import EventType, OrderStatus, PaymentProvider, SubOrderStatus
from contracts.events import (
    EventEnvelope,
    OrderCancelled,
    OrderCreated,
    OrderExpired,
    OrderRefundRequested,
    PaymentPaid,
    PaymentRefunded,
    StockFailed,
    StockReserved,
)
from contracts.ids import uuid7
from messaging.outbox import mark_processed
from orders.metrics import CHECKOUT_FAILED
from orders.models import Order
from orders.services import (
    OUT_OF_STOCK,
    RESERVATION_FAILED,
    cancel_locked,
    clear_cart_quietly,
    commission_rates,
    item_refs,
    pay_locked,
    publish,
)
from orders.state import InvalidTransition, can_transition, lock_order, transition
from py_common.rabbit import PermanentError, SyncHandler
from py_common.web.drf import ApiError

logger = logging.getLogger(__name__)

# Order history reasons.
LATE_PAYMENT = "LATE_PAYMENT"
PAYMENT_REFUNDED = "PAYMENT_REFUNDED"
# order.refund_requested reasons.
LATE_PAYMENT_OUT_OF_STOCK = "LATE_PAYMENT_OUT_OF_STOCK"
ORDER_CANCELLED = "ORDER_CANCELLED"


class NotReserved(ApiError):
    """Payment for an order whose stock is still being reserved. 409; the consumer retries."""

    def __init__(self, order_id: UUID) -> None:
        super().__init__(
            "NOT_RESERVED",
            "The stock of this order is not reserved yet. Try again in a moment.",
            status=409,
            details={"order_id": str(order_id)},
        )


class OrderExpiredError(ApiError):
    def __init__(self, order_id: UUID) -> None:
        super().__init__(
            "ORDER_EXPIRED",
            "The reservation of this order has expired.",
            status=409,
            details={"order_id": str(order_id)},
        )


class StaleOrder(RuntimeError):
    """The order changed between the unlocked read and the lock; a retry reads it again."""


# --- catalog answers ----------------------------------------------------------------------


def on_stock_reserved(envelope: EventEnvelope) -> None:
    event = StockReserved.model_validate(envelope.payload)
    order = _get(event.order_id)
    rates = commission_rates(order) if _awaits_late_reservation(order) else None
    paid = False
    with transaction.atomic():
        if not mark_processed(envelope):
            return
        order = lock_order(event.order_id)
        status = OrderStatus(order.status)
        if status is OrderStatus.PENDING:
            order.reserved_until = event.expires_at
            order.save(update_fields=["reserved_until", "updated_at"])
            transition(order, OrderStatus.RESERVED)
        elif _awaits_late_reservation(order):
            order.reserved_until = event.expires_at
            order.save(update_fields=["reserved_until", "updated_at"])
            pay_locked(order, _fresh(rates), reason=LATE_PAYMENT)
            paid = True
        elif status is OrderStatus.CANCELLED:
            _ignored(envelope, order, "stock held for a cancelled order, releasing again")
            publish(
                order,
                OrderCancelled(
                    order_id=order.id, items=item_refs(order.id), reason=order.cancel_reason
                ),
            )
        elif status is OrderStatus.EXPIRED or (
            status is OrderStatus.REFUNDED and order.late_payment
        ):
            _ignored(envelope, order, "stock held for an expired order, releasing again")
            publish(order, OrderExpired(order_id=order.id, items=item_refs(order.id)))
        else:
            _ignored(envelope, order, "stock already handled")
    if paid:
        clear_cart_quietly(order.customer_id)


def on_stock_failed(envelope: EventEnvelope) -> None:
    event = StockFailed.model_validate(envelope.payload)
    with transaction.atomic():
        if not mark_processed(envelope):
            return
        order = _lock(event.order_id)
        if order.status == OrderStatus.PENDING.value:
            reason = OUT_OF_STOCK if event.reason == OUT_OF_STOCK else RESERVATION_FAILED
            cancel_locked(order, reason)
            CHECKOUT_FAILED.labels(reason=reason).inc()
        elif _awaits_late_reservation(order):
            # Paid too late and the stock is gone: the customer gets the money back.
            transition(order, OrderStatus.REFUNDED, reason=LATE_PAYMENT_OUT_OF_STOCK)
            publish(
                order,
                OrderRefundRequested(
                    order_id=order.id,
                    amount_tiyin=order.total_tiyin,
                    reason=LATE_PAYMENT_OUT_OF_STOCK,
                ),
            )
        else:
            _ignored(envelope, order, "no reservation was awaited")


# --- payment --------------------------------------------------------------------------------


def on_payment_paid(envelope: EventEnvelope) -> None:
    apply_payment(PaymentPaid.model_validate(envelope.payload), envelope=envelope)


def apply_payment(payment: PaymentPaid, *, envelope: EventEnvelope | None = None) -> Order:
    """The single payment path: the ``payment.paid`` consumer and the mock endpoint.

    ``envelope`` is recorded as processed in the same transaction; a redelivery returns
    the order unchanged. Raises NotReserved for a PENDING order.
    """
    order = _get(payment.order_id)
    rates = commission_rates(order) if order.status == OrderStatus.RESERVED.value else None
    paid = False
    with transaction.atomic():
        if envelope is not None and not mark_processed(envelope):
            return order
        order = lock_order(payment.order_id)
        if payment.amount_tiyin != order.total_tiyin:
            logger.warning(
                "payment amount differs from the order total",
                extra={
                    "order_id": str(order.id),
                    "amount_tiyin": payment.amount_tiyin,
                    "total_tiyin": order.total_tiyin,
                },
            )
        status = OrderStatus(order.status)
        if status is OrderStatus.RESERVED:
            # Even past reserved_until: until order.expired is published the catalog holds
            # the stock, and the row lock orders this against the expiry task.
            pay_locked(order, _fresh(rates))
            paid = True
        elif status is OrderStatus.PENDING:
            raise NotReserved(order.id)
        elif status is OrderStatus.EXPIRED and not order.late_payment:
            order.late_payment = True
            order.save(update_fields=["late_payment", "updated_at"])
            publish(
                order,
                OrderCreated(order_id=order.id, items=item_refs(order.id), reserve_retry=True),
            )
        elif status is OrderStatus.CANCELLED:
            logger.warning("payment for a cancelled order", extra={"order_id": str(order.id)})
            publish(
                order,
                OrderRefundRequested(
                    order_id=order.id, amount_tiyin=payment.amount_tiyin, reason=ORDER_CANCELLED
                ),
            )
        else:
            logger.info(
                "payment already handled",
                extra={"order_id": str(order.id), "status": order.status},
            )
    if paid:
        clear_cart_quietly(order.customer_id)
    return order


def mock_pay(order: Order) -> Order:
    """Development payment button: a synthetic ``payment.paid`` through ``apply_payment``.

    Orders a provider would refuse to charge are refused here (no money exists to refund):
    EXPIRED -> ORDER_EXPIRED, CANCELLED / REFUNDED -> INVALID_TRANSITION. A PENDING order
    is refused by ``apply_payment`` itself (NOT_RESERVED).
    """
    if order.status == OrderStatus.EXPIRED.value:
        raise OrderExpiredError(order.id)
    if order.status in (OrderStatus.CANCELLED.value, OrderStatus.REFUNDED.value):
        raise InvalidTransition(order.status, OrderStatus.PAID.value)
    return apply_payment(
        PaymentPaid(
            order_id=order.id,
            transaction_id=uuid7(),
            amount_tiyin=order.total_tiyin,
            provider=PaymentProvider.MOCK,
        )
    )


def on_payment_refunded(envelope: EventEnvelope) -> None:
    event = PaymentRefunded.model_validate(envelope.payload)
    with transaction.atomic():
        if not mark_processed(envelope):
            return
        order = _lock(event.order_id)
        if not can_transition(OrderStatus(order.status), OrderStatus.REFUNDED):
            _ignored(envelope, order, "refund not allowed in this state")
        elif _is_partial_refund(order, event.amount_tiyin):
            _ignored(envelope, order, "partial refund")
        else:
            transition(order, OrderStatus.REFUNDED, reason=PAYMENT_REFUNDED)


# --- wiring ---------------------------------------------------------------------------------

#: What the ``order.q`` consumer does with each event type.
HANDLERS: Mapping[EventType, SyncHandler] = {
    EventType.STOCK_RESERVED: on_stock_reserved,
    EventType.STOCK_FAILED: on_stock_failed,
    EventType.PAYMENT_PAID: on_payment_paid,
    EventType.PAYMENT_REFUNDED: on_payment_refunded,
}


# --- helpers --------------------------------------------------------------------------------


def _get(order_id: UUID) -> Order:
    order = Order.objects.filter(id=order_id).first()
    if order is None:
        raise PermanentError(f"unknown order {order_id}")
    return order


def _lock(order_id: UUID) -> Order:
    try:
        return lock_order(order_id)
    except Order.DoesNotExist as exc:
        raise PermanentError(f"unknown order {order_id}") from exc


def _awaits_late_reservation(order: Order) -> bool:
    return order.status == OrderStatus.EXPIRED.value and order.late_payment


def _fresh(rates: dict[UUID, Decimal] | None) -> dict[UUID, Decimal]:
    if rates is None:
        raise StaleOrder("the order became payable after it was read")
    return rates


def _is_partial_refund(order: Order, amount_tiyin: int) -> bool:
    """A refund smaller than the order while some sub-order is still being fulfilled."""
    if amount_tiyin >= order.total_tiyin:
        return False
    statuses = set(order.sub_orders.values_list("status", flat=True))
    return bool(statuses - {SubOrderStatus.CANCELLED_BY_SELLER.value})


def _ignored(envelope: EventEnvelope, order: Order, why: str) -> None:
    logger.info(
        "event does not change the order",
        extra={
            "event_type": str(envelope.event_type),
            "event_id": str(envelope.event_id),
            "order_id": str(order.id),
            "status": order.status,
            "why": why,
        },
    )
