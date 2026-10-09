"""Weekly seller payouts.

A week runs from Monday 00:00 UTC to the next Monday. Every sub-order delivered in that
week and not yet paid out joins its seller's payout for the week. Running a week again
only adds lines that arrived late, so the job is safe to repeat; a payout already marked
paid is never changed.

    python -m app.payouts run [--week YYYY-MM-DD]   (any day of the week; default: last week)
"""

import argparse
import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import PayoutLine, PayoutStatus, SellerPayout
from app.services.payments import utcnow
from contracts.ids import uuid7

logger = logging.getLogger(__name__)

SCHEDULER_INTERVAL_SECONDS = 3600.0


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def previous_week(now: datetime) -> date:
    return week_start(now.date()) - timedelta(days=7)


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


async def build_payouts(sessions: async_sessionmaker[AsyncSession], period_start: date) -> int:
    """Assign the week's delivered lines to payouts. Returns how many lines were added."""
    period_start = week_start(period_start)
    period_end = period_start + timedelta(days=7)
    async with sessions.begin() as session:
        lines = (
            await session.scalars(
                select(PayoutLine)
                .where(
                    PayoutLine.payout_id.is_(None),
                    PayoutLine.cancelled.is_(False),
                    PayoutLine.delivered_at >= _midnight(period_start),
                    PayoutLine.delivered_at < _midnight(period_end),
                )
                .order_by(PayoutLine.seller_id, PayoutLine.delivered_at)
                .with_for_update(skip_locked=True)
            )
        ).all()
        by_seller: dict[UUID, list[PayoutLine]] = defaultdict(list)
        for line in lines:
            by_seller[line.seller_id].append(line)

        added = 0
        for seller_id, seller_lines in by_seller.items():
            payout = await _payout_for(session, seller_id, period_start, period_end)
            if payout.status != PayoutStatus.PENDING:
                logger.warning(
                    "late delivered lines for a paid payout",
                    extra={"payout_id": str(payout.id), "lines": len(seller_lines)},
                )
                continue
            for line in seller_lines:
                line.payout_id = payout.id
                payout.gross_tiyin += line.gross_tiyin
                payout.commission_tiyin += line.commission_tiyin
                payout.net_tiyin += line.net_tiyin
            added += len(seller_lines)
    logger.info(
        "payouts built",
        extra={"period_start": period_start.isoformat(), "lines": added, "sellers": len(by_seller)},
    )
    return added


async def _payout_for(
    session: AsyncSession, seller_id: UUID, period_start: date, period_end: date
) -> SellerPayout:
    """The seller's payout for the week, created on first use (concurrency safe)."""
    await session.execute(
        insert(SellerPayout)
        .values(
            id=uuid7(),
            seller_id=seller_id,
            period_start=period_start,
            period_end=period_end,
            gross_tiyin=0,
            commission_tiyin=0,
            net_tiyin=0,
            status=PayoutStatus.PENDING.value,
        )
        .on_conflict_do_nothing(constraint="uq_seller_payouts_seller_period")
    )
    payout = await session.scalar(
        select(SellerPayout)
        .where(SellerPayout.seller_id == seller_id, SellerPayout.period_start == period_start)
        .with_for_update()
    )
    assert payout is not None
    return payout


class PayoutScheduler:
    """Builds last week's payouts once an hour; repeats are harmless."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        interval: float = SCHEDULER_INTERVAL_SECONDS,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._sessions = sessions
        self._interval = interval
        self._clock = clock
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="payment-payouts")

    async def _loop(self) -> None:
        while True:
            try:
                await build_payouts(self._sessions, previous_week(self._clock()))
            except Exception:
                logger.warning("payout run failed", exc_info=True)
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)


async def _run(week: date | None) -> int:
    from app.core.config import load_settings
    from app.db import make_engine, make_sessionmaker

    engine = make_engine(load_settings().database_url)
    try:
        period = week or previous_week(utcnow())
        return await build_payouts(make_sessionmaker(engine), period)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.payouts")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="build the payouts of one week")
    run.add_argument("--week", type=date.fromisoformat, help="any day of the week (UTC)")
    args = parser.parse_args()
    added = asyncio.run(_run(args.week))
    print(f"{added} lines added to payouts")


if __name__ == "__main__":
    main()
