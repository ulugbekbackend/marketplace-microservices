"""``payment.q`` consumer.

    order.refund_requested    give money back from the order's paid transaction
    order.paid                one payout line per sub-order (commission snapshot)
    sub_order.status_changed  DELIVERED makes a line payable, CANCELLED_BY_SELLER drops it

Each event is recorded in ``processed_events`` in the same transaction as its effect, so a
redelivery is a no-op and a failed attempt leaves nothing behind.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import PayoutLine, ProcessedEvent, TransactionState
from app.services import payments
from contracts.enums import EventType, SubOrderStatus
from contracts.events import (
    EventEnvelope,
    OrderPaid,
    OrderRefundRequested,
    SubOrderStatusChanged,
)
from py_common.consumer import Outcome
from py_common.context import request_context

logger = logging.getLogger(__name__)

SERVICE = "payment"

#: Payme's cancel reason for a refund; stored on transactions refunded in full.
REASON_REFUND = 5

Handler = Callable[[AsyncSession, EventEnvelope], Awaitable[None]]


class LineNotYetKnownError(RuntimeError):
    """A sub-order event arrived before ``order.paid``; the retry will find the line."""


async def on_refund_requested(session: AsyncSession, envelope: EventEnvelope) -> None:
    event = OrderRefundRequested.model_validate(envelope.payload)
    transaction = await payments.performed_for_order(session, event.order_id)
    if transaction is None:
        # Nothing was charged through this service (e.g. the order's development mock
        # payment), or a provider cancel already returned the whole amount.
        logger.warning(
            "refund requested without a paid transaction",
            extra={"order_id": str(event.order_id), "reason": event.reason},
        )
        return
    remaining = transaction.amount_tiyin - await payments.refunded(session, transaction.id)
    amount = min(event.amount_tiyin, remaining)
    if amount <= 0:
        logger.warning("refund over the paid amount", extra={"order_id": str(event.order_id)})
        return
    now = envelope.occurred_at
    # Providers are told locally: no live merchant credentials exist in this project.
    payments.record_refund(session, transaction, amount, reason=event.reason, now=now)
    if amount == remaining:
        transaction.state = TransactionState.CANCELLED_AFTER_PERFORM
        transaction.cancel_time = now
        transaction.reason = REASON_REFUND


async def on_order_paid(session: AsyncSession, envelope: EventEnvelope) -> None:
    event = OrderPaid.model_validate(envelope.payload)
    rows = [
        {
            "sub_order_id": sub.id,
            "order_id": event.order_id,
            "seller_id": sub.seller_id,
            "gross_tiyin": sub.subtotal_tiyin,
            "commission_tiyin": sub.commission_tiyin,
            "net_tiyin": sub.subtotal_tiyin - sub.commission_tiyin,
        }
        for sub in event.sub_orders
    ]
    await session.execute(
        insert(PayoutLine).values(rows).on_conflict_do_nothing(index_elements=["sub_order_id"])
    )


async def on_sub_order_status_changed(session: AsyncSession, envelope: EventEnvelope) -> None:
    event = SubOrderStatusChanged.model_validate(envelope.payload)
    if event.status is SubOrderStatus.DELIVERED:
        await _update_line(session, event, delivered_at=envelope.occurred_at)
    elif event.status is SubOrderStatus.CANCELLED_BY_SELLER:
        await _update_line(session, event, cancelled=True)


async def _update_line(
    session: AsyncSession,
    event: SubOrderStatusChanged,
    *,
    delivered_at: datetime | None = None,
    cancelled: bool = False,
) -> None:
    values: dict[str, object] = {"cancelled": True} if cancelled else {}
    if delivered_at is not None:
        values["delivered_at"] = delivered_at
    result = await session.execute(
        update(PayoutLine)
        .where(PayoutLine.sub_order_id == event.sub_order_id)
        .values(**values)
        .returning(PayoutLine.sub_order_id)
    )
    if result.first() is None:
        raise LineNotYetKnownError(f"no payout line for sub-order {event.sub_order_id}")


HANDLERS: Mapping[EventType, Handler] = {
    EventType.ORDER_REFUND_REQUESTED: on_refund_requested,
    EventType.ORDER_PAID: on_order_paid,
    EventType.SUB_ORDER_STATUS_CHANGED: on_sub_order_status_changed,
}


class PaymentEventHandler:
    """What the broker consumer calls for each delivery. Raising means retry or DLQ."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def __call__(self, body: bytes) -> Outcome:
        envelope = EventEnvelope.model_validate_json(body)
        handler = HANDLERS.get(envelope.event_type)
        if handler is None:
            return Outcome.IGNORED
        with request_context(correlation_id=envelope.correlation_id):
            async with self._sessions.begin() as session:
                # A concurrent duplicate waits on the primary key, then sees the conflict.
                first = await session.execute(
                    insert(ProcessedEvent)
                    .values(event_id=envelope.event_id, event_type=envelope.event_type.value)
                    .on_conflict_do_nothing()
                    .returning(ProcessedEvent.event_id)
                )
                if first.first() is None:
                    logger.info("duplicate event", extra={"event_id": str(envelope.event_id)})
                    return Outcome.DUPLICATE
                await handler(session, envelope)
        return Outcome.HANDLED
