"""Payment tables. Money is integer tiyin, ids are UUID, time is UTC ``timestamptz``."""

from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from contracts.ids import uuid7

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TransactionState(IntEnum):
    """Payme's numbering, used for every provider: the Payme API returns it as is."""

    CREATED = 1
    PERFORMED = 2
    CANCELLED = -1
    CANCELLED_AFTER_PERFORM = -2


class RefundStatus(StrEnum):
    DONE = "done"


class PayoutStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"


class Transaction(Base):
    """One attempt to charge an order through a provider.

    ``external_id`` is the provider's id (Payme transaction id, Click click_trans_id);
    ``number`` is the integer id Click wants back as merchant_prepare_id.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_transactions_provider_external_id"),
        # One order, at most one transaction that is still waiting to be performed.
        Index(
            "uq_transactions_active_order",
            "order_id",
            unique=True,
            postgresql_where=text("state = 1"),
        ),
        Index("ix_transactions_order_id", "order_id"),
        Index("ix_transactions_provider_create_time", "provider", "create_time"),
        CheckConstraint("amount_tiyin > 0", name="amount_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    order_id: Mapped[UUID]
    provider: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(64))
    amount_tiyin: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[int] = mapped_column(SmallInteger, default=TransactionState.CREATED)
    provider_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    perform_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount_tiyin > 0", name="amount_positive"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    transaction_id: Mapped[UUID] = mapped_column(ForeignKey("transactions.id"), index=True)
    amount_tiyin: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=RefundStatus.DONE)
    reason: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SellerPayout(Base):
    """What one seller is owed for one week (Monday 00:00 UTC to the next Monday)."""

    __tablename__ = "seller_payouts"
    __table_args__ = (
        UniqueConstraint("seller_id", "period_start", name="uq_seller_payouts_seller_period"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    seller_id: Mapped[UUID]
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    gross_tiyin: Mapped[int] = mapped_column(BigInteger, default=0)
    commission_tiyin: Mapped[int] = mapped_column(BigInteger, default=0)
    net_tiyin: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(16), default=PayoutStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayoutLine(Base):
    """One paid sub-order with the commission snapshot of ``order.paid``.

    It joins a payout once the sub-order is delivered; a sub-order the seller cancelled
    never does.
    """

    __tablename__ = "payout_lines"
    __table_args__ = (
        Index(
            "ix_payout_lines_unassigned_delivered",
            "delivered_at",
            postgresql_where=text("payout_id IS NULL AND cancelled = false"),
        ),
    )

    sub_order_id: Mapped[UUID] = mapped_column(primary_key=True)
    order_id: Mapped[UUID]
    seller_id: Mapped[UUID] = mapped_column(index=True)
    gross_tiyin: Mapped[int] = mapped_column(BigInteger)
    commission_tiyin: Mapped[int] = mapped_column(BigInteger)
    net_tiyin: Mapped[int] = mapped_column(BigInteger)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled: Mapped[bool] = mapped_column(default=False)
    payout_id: Mapped[UUID | None] = mapped_column(ForeignKey("seller_payouts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Outbox(Base):
    """One event waiting to be published, written in the transaction of its change."""

    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_unpublished", "id", postgresql_where=text("published_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[UUID]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessedEvent(Base):
    """Event ids already handled by the consumer: a redelivery is skipped."""

    __tablename__ = "processed_events"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
