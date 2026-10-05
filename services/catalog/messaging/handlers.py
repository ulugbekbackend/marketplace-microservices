"""Handlers for the events the catalog consumes (queue ``catalog.q``).

Each handler runs in one transaction with its processed-events row and the events it
writes, so a redelivery is skipped and a failure leaves nothing behind.
"""

import logging
from collections.abc import Mapping

from django.db import transaction
from django.utils import timezone

from contracts.enums import EventType
from contracts.events import (
    EventEnvelope,
    Frozen,
    OrderCancelled,
    OrderCreated,
    OrderExpired,
    OrderPaid,
    StockFailed,
    StockReserved,
    build_event,
)
from messaging.outbox import add_to_outbox, mark_processed
from products import stock
from products.reservations import NotReserved, ReservationItem, Reserved
from py_common.rabbit import PermanentError, SyncHandler
from sellers.services import handle_seller_approved

logger = logging.getLogger(__name__)

PRODUCER = "catalog"


def _first_time(envelope: EventEnvelope) -> bool:
    if mark_processed(envelope):
        return True
    logger.info(
        "event already processed",
        extra={"event_id": str(envelope.event_id), "event_type": str(envelope.event_type)},
    )
    return False


def _emit(payload: Frozen, cause: EventEnvelope) -> None:
    add_to_outbox(
        build_event(
            payload,
            producer=PRODUCER,
            correlation_id=cause.correlation_id,
            occurred_at=timezone.now(),
        )
    )


def on_order_created(envelope: EventEnvelope) -> None:
    """Hold stock for a new order (or again, for a late payment after expiry)."""
    payload = OrderCreated.model_validate(envelope.payload)
    items = [ReservationItem(item.variant_id, item.qty) for item in payload.items]
    with transaction.atomic():
        if not _first_time(envelope):
            return
        result = stock.reserve(
            payload.order_id,
            items,
            reserved_at=envelope.occurred_at,
            correlation_id=envelope.correlation_id,
        )
        if isinstance(result, Reserved):
            _emit(StockReserved(order_id=payload.order_id, expires_at=result.expires_at), envelope)
        else:
            _emit(
                StockFailed(
                    order_id=payload.order_id,
                    reason=result.reason,
                    variant_ids=result.variant_ids,
                ),
                envelope,
            )


def on_order_paid(envelope: EventEnvelope) -> None:
    """The reserved units are sold."""
    payload = OrderPaid.model_validate(envelope.payload)
    with transaction.atomic():
        if not _first_time(envelope):
            return
        try:
            stock.commit(payload.order_id, correlation_id=envelope.correlation_id)
        except NotReserved as exc:
            # Retrying cannot create a reservation: the saga is broken, a human looks at it.
            raise PermanentError(f"order {payload.order_id} holds no stock to commit") from exc


def on_order_released(envelope: EventEnvelope) -> None:
    """``order.expired`` or ``order.cancelled``: give the held units back.

    Only units reserved by an ``order.created`` that occurred no later than this event:
    a retried or late ``order.expired`` must not free what a late payment reserved again
    after the expiry. Both timestamps come from the order service's clock, so they are
    compared as they are, without a tolerance.
    """
    model = OrderExpired if envelope.event_type is EventType.ORDER_EXPIRED else OrderCancelled
    payload = model.model_validate(envelope.payload)
    with transaction.atomic():
        if not _first_time(envelope):
            return
        freed = stock.release(
            payload.order_id,
            reserved_before=envelope.occurred_at,
            correlation_id=envelope.correlation_id,
        )
        if not freed:
            logger.info(
                "nothing to release",
                extra={"order_id": str(payload.order_id), "event_id": str(envelope.event_id)},
            )


def on_seller_approved(envelope: EventEnvelope) -> None:
    handle_seller_approved(envelope)


HANDLERS: Mapping[EventType, SyncHandler] = {
    EventType.ORDER_CREATED: on_order_created,
    EventType.ORDER_PAID: on_order_paid,
    EventType.ORDER_EXPIRED: on_order_released,
    EventType.ORDER_CANCELLED: on_order_released,
    EventType.SELLER_APPROVED: on_seller_approved,
}
