"""Transactional outbox on SQLAlchemy: ``add_event`` writes the row in the caller's
transaction, ``OutboxRelay`` publishes unpublished rows in the background.

A row is stamped only after the broker confirmed it, so a crash means a duplicate
delivery, never a lost event. Consumers are idempotent by ``event_id``.

The relay runs in this process, so a commit that carried outbox rows wakes it at once;
the interval only bounds the wait when nothing commits.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.models import Outbox
from contracts.events import EventEnvelope, Frozen, build_event
from contracts.ids import uuid7
from py_common.context import get_correlation_id

logger = logging.getLogger(__name__)

#: The ``producer`` field of every envelope this service publishes.
PRODUCER = "payment"

#: Longest pause between relay attempts while the database or broker keeps failing.
MAX_BACKOFF_SECONDS = 30.0

#: ``Session.info`` flag: this transaction added outbox rows.
_PENDING_FLAG = "outbox_pending"

#: Running relays, woken after every commit that added outbox rows.
_relays: set["OutboxRelay"] = set()


@event.listens_for(Session, "after_commit")
def _wake_relays(session: Session) -> None:
    if session.info.pop(_PENDING_FLAG, False):
        for relay in _relays:
            relay.wake()


@event.listens_for(Session, "after_rollback")
def _forget_rows(session: Session) -> None:
    session.info.pop(_PENDING_FLAG, None)


class AsyncPublisher(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...


def add_event(session: AsyncSession, payload: Frozen, *, now: datetime | None = None) -> Outbox:
    """Stage an event in the session; it commits together with the business change."""
    envelope = build_event(
        payload,
        producer=PRODUCER,
        correlation_id=get_correlation_id() or uuid7(),
        occurred_at=now or datetime.now(UTC),
    )
    row = Outbox(
        event_id=envelope.event_id,
        event_type=envelope.event_type.value,
        correlation_id=envelope.correlation_id,
        occurred_at=envelope.occurred_at,
        version=envelope.version,
        payload=envelope.payload,
    )
    session.add(row)
    session.info[_PENDING_FLAG] = True
    return row


def to_envelope(row: Outbox) -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": row.event_id,
            "event_type": row.event_type,
            "occurred_at": row.occurred_at,
            "producer": PRODUCER,
            "correlation_id": row.correlation_id,
            "version": row.version,
            "payload": row.payload,
        }
    )


async def publish_pending(
    sessions: async_sessionmaker[AsyncSession], publisher: AsyncPublisher, *, limit: int = 100
) -> int:
    """Publish one batch. The rows stay locked (SKIP LOCKED) until they are stamped, so
    two relays never publish the same row at the same time."""
    async with sessions.begin() as session:
        rows = (
            await session.scalars(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        published: list[int] = []
        for row in rows:
            try:
                await publisher.publish(to_envelope(row))
            except Exception:
                logger.exception("outbox publish failed", extra={"event_id": str(row.event_id)})
                break
            published.append(row.id)
        if published:
            await session.execute(
                update(Outbox)
                .where(Outbox.id.in_(published))
                .values(published_at=datetime.now(UTC))
            )
    return len(published)


class OutboxRelay:
    """Background task: publish a batch, sleep when the outbox is empty, back off on errors."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        publisher: AsyncPublisher,
        *,
        interval: float = 1.0,
        batch: int = 100,
    ) -> None:
        self._sessions = sessions
        self._publisher = publisher
        self._interval = interval
        self._batch = batch
        self._task: asyncio.Task[None] | None = None
        self._woken = asyncio.Event()

    def start(self) -> None:
        _relays.add(self)
        self._task = asyncio.create_task(self._loop(), name="payment-outbox-relay")

    def wake(self) -> None:
        """Cut the current wait short: new rows were committed."""
        self._woken.set()

    async def _idle(self) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._woken.wait(), timeout=self._interval)
        self._woken.clear()

    async def _loop(self) -> None:
        failures = 0
        while True:
            try:
                count = await publish_pending(self._sessions, self._publisher, limit=self._batch)
            except Exception:
                failures += 1
                # The first failure in full, then a short line every tenth while it lasts.
                if failures == 1 or failures % 10 == 0:
                    logger.warning(
                        "outbox relay iteration failed",
                        exc_info=failures == 1,
                        extra={"failures": failures},
                    )
                await asyncio.sleep(min(self._interval * 2**failures, MAX_BACKOFF_SECONDS))
                continue
            if failures:
                logger.info("outbox relay recovered", extra={"failures": failures})
                failures = 0
            if count < self._batch:
                await self._idle()

    async def stop(self) -> None:
        _relays.discard(self)
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
