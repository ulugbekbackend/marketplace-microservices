"""Provider independent transaction state machine.

Every state change and the event it produces are written in the caller's database
transaction, so ``payment.paid`` / ``payment.refunded`` leave exactly when the change
commits. Callers lock the transaction row (``lock``) before changing it, which makes a
repeated webhook wait for the first one and then see its result.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Refund, Transaction, TransactionState
from app.outbox import add_event
from contracts.enums import PaymentProvider
from contracts.events import PaymentPaid, PaymentRefunded
from contracts.ids import uuid7


def utcnow() -> datetime:
    return datetime.now(UTC)


def by_external_id(provider: PaymentProvider, external_id: str) -> Select[Transaction]:
    return select(Transaction).where(
        Transaction.provider == provider.value, Transaction.external_id == external_id
    )


async def lock(
    session: AsyncSession, provider: PaymentProvider, external_id: str
) -> Transaction | None:
    return await session.scalar(by_external_id(provider, external_id).with_for_update())


async def active_for_order(session: AsyncSession, order_id: UUID) -> Transaction | None:
    """The order's transaction that is created but not yet performed or cancelled."""
    return await session.scalar(
        select(Transaction).where(
            Transaction.order_id == order_id, Transaction.state == TransactionState.CREATED
        )
    )


async def performed_for_order(session: AsyncSession, order_id: UUID) -> Transaction | None:
    """The order's paid transaction (the latest, should a provider ever pay twice)."""
    return await session.scalar(
        select(Transaction)
        .where(Transaction.order_id == order_id, Transaction.state == TransactionState.PERFORMED)
        .order_by(Transaction.perform_time.desc())
        .limit(1)
        .with_for_update()
    )


def create(
    session: AsyncSession,
    *,
    order_id: UUID,
    provider: PaymentProvider,
    external_id: str,
    amount_tiyin: int,
    now: datetime,
    provider_time: datetime | None = None,
) -> Transaction:
    transaction = Transaction(
        id=uuid7(),
        order_id=order_id,
        provider=provider.value,
        external_id=external_id,
        amount_tiyin=amount_tiyin,
        state=TransactionState.CREATED,
        create_time=now,
        provider_time=provider_time,
    )
    session.add(transaction)
    return transaction


def perform(session: AsyncSession, transaction: Transaction, *, now: datetime) -> bool:
    """CREATED -> PERFORMED and ``payment.paid``. Returns False when nothing changed."""
    if transaction.state != TransactionState.CREATED:
        return False
    transaction.state = TransactionState.PERFORMED
    transaction.perform_time = now
    add_event(
        session,
        PaymentPaid(
            order_id=transaction.order_id,
            transaction_id=transaction.id,
            amount_tiyin=transaction.amount_tiyin,
            provider=PaymentProvider(transaction.provider),
        ),
        now=now,
    )
    return True


async def cancel(
    session: AsyncSession, transaction: Transaction, *, reason: int | None, now: datetime
) -> bool:
    """CREATED -> CANCELLED; PERFORMED -> CANCELLED_AFTER_PERFORM with a refund of what is
    left of the payment. Returns False when the transaction was already cancelled."""
    if transaction.state == TransactionState.CREATED:
        transaction.state = TransactionState.CANCELLED
    elif transaction.state == TransactionState.PERFORMED:
        transaction.state = TransactionState.CANCELLED_AFTER_PERFORM
        remaining = transaction.amount_tiyin - await refunded(session, transaction.id)
        if remaining > 0:
            record_refund(session, transaction, remaining, reason="PROVIDER_CANCELLED", now=now)
    else:
        return False
    transaction.cancel_time = now
    transaction.reason = reason
    return True


async def refunded(session: AsyncSession, transaction_id: UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(Refund.amount_tiyin), 0)).where(
            Refund.transaction_id == transaction_id
        )
    )
    return int(total or 0)


def record_refund(
    session: AsyncSession,
    transaction: Transaction,
    amount_tiyin: int,
    *,
    reason: str,
    now: datetime,
) -> Refund:
    refund = Refund(
        id=uuid7(), transaction_id=transaction.id, amount_tiyin=amount_tiyin, reason=reason
    )
    session.add(refund)
    add_event(
        session,
        PaymentRefunded(order_id=transaction.order_id, amount_tiyin=amount_tiyin),
        now=now,
    )
    return refund
