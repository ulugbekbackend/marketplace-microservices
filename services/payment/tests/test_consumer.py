"""``payment.q`` consumer: refunds, payout lines, sub-order statuses, idempotency."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.consumers.events import LineNotYetKnownError, PaymentEventHandler
from app.models import PayoutLine, Refund, Transaction, TransactionState
from app.services import payments
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contracts.enums import EventType, PaymentProvider, SubOrderStatus
from contracts.events import (
    Frozen,
    OrderItemRef,
    OrderPaid,
    OrderRefundRequested,
    StockFailed,
    SubOrderRef,
    SubOrderStatusChanged,
    build_event,
)
from py_common.consumer import Outcome
from tests.conftest import outbox_events

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def body(payload: Frozen, *, occurred_at: datetime = NOW, event_id: UUID | None = None) -> bytes:
    envelope = build_event(
        payload,
        producer="order",
        correlation_id=uuid4(),
        occurred_at=occurred_at,
        event_id=event_id,
    )
    return envelope.model_dump_json().encode()


@pytest.fixture
def handle(sessions: async_sessionmaker[AsyncSession]) -> PaymentEventHandler:
    return PaymentEventHandler(sessions)


async def paid_transaction(
    sessions: async_sessionmaker[AsyncSession], amount: int = 1_000_000
) -> Transaction:
    async with sessions.begin() as session:
        transaction = payments.create(
            session,
            order_id=uuid4(),
            provider=PaymentProvider.PAYME,
            external_id=uuid4().hex,
            amount_tiyin=amount,
            now=NOW,
        )
        payments.perform(session, transaction, now=NOW)
    return transaction


async def load(sessions: async_sessionmaker[AsyncSession], transaction_id: UUID) -> Transaction:
    async with sessions() as session:
        transaction = await session.get(Transaction, transaction_id)
    assert transaction is not None
    return transaction


async def refunds(sessions: async_sessionmaker[AsyncSession]) -> list[Refund]:
    async with sessions() as session:
        return list((await session.scalars(select(Refund).order_by(Refund.created_at))).all())


def refund_event(order_id: UUID, amount: int, reason: str = "CANCELLED_BY_SELLER") -> bytes:
    return body(OrderRefundRequested(order_id=order_id, amount_tiyin=amount, reason=reason))


# --- refunds --------------------------------------------------------------------------


async def test_full_refund_cancels_the_transaction(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    transaction = await paid_transaction(sessions)

    assert await handle(refund_event(transaction.order_id, 1_000_000)) is Outcome.HANDLED

    stored = await load(sessions, transaction.id)
    assert stored.state == TransactionState.CANCELLED_AFTER_PERFORM
    assert stored.reason == 5
    assert [r.amount_tiyin for r in await refunds(sessions)] == [1_000_000]
    events = await outbox_events(sessions)
    assert events[-1].event_type == EventType.PAYMENT_REFUNDED.value
    assert events[-1].payload == {"order_id": str(transaction.order_id), "amount_tiyin": 1_000_000}


async def test_partial_refunds_add_up_to_the_payment(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    transaction = await paid_transaction(sessions)

    await handle(refund_event(transaction.order_id, 300_000))
    assert (await load(sessions, transaction.id)).state == TransactionState.PERFORMED

    await handle(refund_event(transaction.order_id, 700_000))
    assert (await load(sessions, transaction.id)).state == TransactionState.CANCELLED_AFTER_PERFORM
    assert [r.amount_tiyin for r in await refunds(sessions)] == [300_000, 700_000]


async def test_refund_is_capped_at_what_is_left(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    transaction = await paid_transaction(sessions)
    await handle(refund_event(transaction.order_id, 800_000))

    await handle(refund_event(transaction.order_id, 800_000))

    assert [r.amount_tiyin for r in await refunds(sessions)] == [800_000, 200_000]


async def test_refund_without_a_paid_transaction_is_ignored(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    assert await handle(refund_event(uuid4(), 500_000)) is Outcome.HANDLED

    assert await refunds(sessions) == []
    assert await outbox_events(sessions) == []


async def test_redelivered_refund_is_a_duplicate(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    transaction = await paid_transaction(sessions)
    event = refund_event(transaction.order_id, 300_000)

    assert await handle(event) is Outcome.HANDLED
    assert await handle(event) is Outcome.DUPLICATE

    assert len(await refunds(sessions)) == 1


async def test_other_events_are_ignored(handle: PaymentEventHandler) -> None:
    assert await handle(body(StockFailed(order_id=uuid4(), reason="x"))) is Outcome.IGNORED


# --- payout lines ---------------------------------------------------------------------


def order_paid(seller_a: UUID, seller_b: UUID) -> OrderPaid:
    return OrderPaid(
        order_id=uuid4(),
        customer_id=uuid4(),
        sub_orders=[
            SubOrderRef(
                id=uuid4(),
                seller_id=seller,
                items=[OrderItemRef(variant_id=uuid4(), qty=1)],
                subtotal_tiyin=subtotal,
                commission_tiyin=commission,
            )
            for seller, subtotal, commission in [
                (seller_a, 2_000_010, 200_001),
                (seller_b, 333_336, 28_334),
            ]
        ],
    )


async def lines(sessions: async_sessionmaker[AsyncSession]) -> dict[UUID, PayoutLine]:
    async with sessions() as session:
        return {line.sub_order_id: line for line in (await session.scalars(select(PayoutLine)))}


async def test_order_paid_stores_one_line_per_sub_order(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seller_a, seller_b = uuid4(), uuid4()
    event = order_paid(seller_a, seller_b)

    await handle(body(event))
    await handle(body(event))  # another event id with the same sub-orders: no new lines

    stored = await lines(sessions)
    assert len(stored) == 2
    first = stored[event.sub_orders[0].id]
    assert (first.seller_id, first.gross_tiyin, first.commission_tiyin, first.net_tiyin) == (
        seller_a,
        2_000_010,
        200_001,
        1_800_009,
    )
    assert first.delivered_at is None and first.cancelled is False


async def test_delivered_and_cancelled_sub_orders_update_their_lines(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    event = order_paid(uuid4(), uuid4())
    await handle(body(event))
    delivered, cancelled = event.sub_orders
    delivered_at = NOW + timedelta(days=2)

    for sub, status, when in [
        (delivered, SubOrderStatus.SHIPPED, NOW + timedelta(days=1)),
        (delivered, SubOrderStatus.DELIVERED, delivered_at),
        (cancelled, SubOrderStatus.CANCELLED_BY_SELLER, NOW),
    ]:
        change = SubOrderStatusChanged(
            sub_order_id=sub.id,
            order_id=event.order_id,
            seller_id=sub.seller_id,
            customer_id=event.customer_id,
            status=status,
        )
        assert await handle(body(change, occurred_at=when)) is Outcome.HANDLED

    stored = await lines(sessions)
    assert stored[delivered.id].delivered_at == delivered_at
    assert stored[cancelled.id].cancelled is True


async def test_status_before_order_paid_fails_so_it_is_retried(
    handle: PaymentEventHandler, sessions: async_sessionmaker[AsyncSession]
) -> None:
    change = SubOrderStatusChanged(
        sub_order_id=uuid4(),
        order_id=uuid4(),
        seller_id=uuid4(),
        customer_id=uuid4(),
        status=SubOrderStatus.DELIVERED,
    )
    event = body(change)

    with pytest.raises(LineNotYetKnownError):
        await handle(event)

    # The failed attempt left no processed mark: the redelivery is handled, not skipped.
    with pytest.raises(LineNotYetKnownError):
        await handle(event)
