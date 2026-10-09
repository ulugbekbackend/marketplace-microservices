"""Weekly payouts: which lines join, repeated runs, and the seller API."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.models import PayoutLine, PayoutStatus, SellerPayout
from app.payouts import build_payouts, previous_week, week_start
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contracts.enums import UserRole
from tests.conftest import user_headers

WEEK = date(2026, 9, 28)  # a Monday
IN_WEEK = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)


async def add_line(
    sessions: async_sessionmaker[AsyncSession],
    seller_id: UUID,
    *,
    gross: int = 1_000_000,
    commission: int = 100_000,
    delivered_at: datetime | None = IN_WEEK,
    cancelled: bool = False,
) -> UUID:
    sub_order_id = uuid4()
    async with sessions.begin() as session:
        session.add(
            PayoutLine(
                sub_order_id=sub_order_id,
                order_id=uuid4(),
                seller_id=seller_id,
                gross_tiyin=gross,
                commission_tiyin=commission,
                net_tiyin=gross - commission,
                delivered_at=delivered_at,
                cancelled=cancelled,
            )
        )
    return sub_order_id


async def payouts(sessions: async_sessionmaker[AsyncSession]) -> list[SellerPayout]:
    async with sessions() as session:
        return list(
            (await session.scalars(select(SellerPayout).order_by(SellerPayout.seller_id))).all()
        )


def test_week_helpers() -> None:
    assert week_start(date(2026, 10, 4)) == date(2026, 9, 28)  # Sunday -> its Monday
    assert week_start(WEEK) == WEEK
    assert previous_week(datetime(2026, 10, 5, 0, 30, tzinfo=UTC)) == WEEK


async def test_delivered_lines_are_summed_per_seller(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    seller_a, seller_b = sorted([uuid4(), uuid4()])
    await add_line(sessions, seller_a, gross=1_000_000, commission=100_000)
    await add_line(sessions, seller_a, gross=500_005, commission=42_501)
    await add_line(sessions, seller_b, gross=200_000, commission=17_000)

    assert await build_payouts(sessions, date(2026, 10, 1)) == 3

    first, second = await payouts(sessions)
    assert (first.seller_id, first.period_start, first.period_end) == (
        seller_a,
        WEEK,
        WEEK + timedelta(days=7),
    )
    assert (first.gross_tiyin, first.commission_tiyin, first.net_tiyin) == (
        1_500_005,
        142_501,
        1_357_504,
    )
    assert first.status == PayoutStatus.PENDING
    assert (second.seller_id, second.net_tiyin) == (seller_b, 183_000)


async def test_only_lines_delivered_in_the_week_and_not_cancelled_join(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    seller = uuid4()
    await add_line(sessions, seller, gross=100_000, commission=0)
    await add_line(sessions, seller, delivered_at=None)
    await add_line(sessions, seller, cancelled=True)
    await add_line(sessions, seller, delivered_at=datetime(2026, 9, 27, 23, 59, tzinfo=UTC))
    await add_line(sessions, seller, delivered_at=datetime(2026, 10, 5, 0, 0, tzinfo=UTC))

    assert await build_payouts(sessions, WEEK) == 1

    [payout] = await payouts(sessions)
    assert payout.gross_tiyin == 100_000


async def test_running_a_week_again_only_adds_late_lines(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    seller = uuid4()
    await add_line(sessions, seller, gross=100_000, commission=10_000)
    await build_payouts(sessions, WEEK)

    assert await build_payouts(sessions, WEEK) == 0
    await add_line(sessions, seller, gross=50_000, commission=5_000)
    assert await build_payouts(sessions, WEEK) == 1

    [payout] = await payouts(sessions)
    assert (payout.gross_tiyin, payout.net_tiyin) == (150_000, 135_000)


async def test_a_paid_payout_is_never_changed(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    seller = uuid4()
    await add_line(sessions, seller, gross=100_000, commission=10_000)
    await build_payouts(sessions, WEEK)
    async with sessions.begin() as session:
        await session.execute(update(SellerPayout).values(status=PayoutStatus.PAID.value))
    late = await add_line(sessions, seller, gross=70_000, commission=7_000)

    assert await build_payouts(sessions, WEEK) == 0

    [payout] = await payouts(sessions)
    assert payout.gross_tiyin == 100_000
    async with sessions() as session:
        line = await session.get(PayoutLine, late)
    assert line is not None and line.payout_id is None


# --- seller API -----------------------------------------------------------------------


@pytest.fixture
def seller() -> tuple[UUID, UUID]:
    """(user id, seller id)."""
    return uuid4(), uuid4()


async def test_seller_sees_own_payouts_newest_first(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seller: tuple[UUID, UUID],
) -> None:
    user_id, seller_id = seller
    await add_line(sessions, seller_id, gross=100_000, commission=10_000)
    await add_line(sessions, seller_id, gross=20_000, commission=2_000)
    await add_line(
        sessions, seller_id, delivered_at=IN_WEEK + timedelta(days=7), gross=300, commission=30
    )
    await add_line(sessions, uuid4())  # another seller
    await build_payouts(sessions, WEEK)
    await build_payouts(sessions, WEEK + timedelta(days=7))

    response = await client.get(
        "/api/payments/seller/payouts/",
        headers=user_headers(user_id, UserRole.SELLER, seller_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total"], body["page"], body["page_size"]) == (2, 1, 20)
    newest, older = body["items"]
    assert newest["period_start"] == "2026-10-05"
    assert (newest["net_tiyin"], newest["lines_count"]) == (270, 1)
    assert older["period_start"] == "2026-09-28"
    assert older["period_end"] == "2026-10-05"
    assert (older["gross_tiyin"], older["commission_tiyin"], older["net_tiyin"]) == (
        120_000,
        12_000,
        108_000,
    )
    assert (older["status"], older["lines_count"]) == ("pending", 2)


async def test_payouts_are_paginated(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seller: tuple[UUID, UUID],
) -> None:
    user_id, seller_id = seller
    for weeks in range(3):
        await add_line(sessions, seller_id, delivered_at=IN_WEEK + timedelta(days=7 * weeks))
        await build_payouts(sessions, WEEK + timedelta(days=7 * weeks))

    response = await client.get(
        "/api/payments/seller/payouts/",
        params={"page": 2, "page_size": 2},
        headers=user_headers(user_id, UserRole.SELLER, seller_id),
    )

    body = response.json()
    assert body["total"] == 3
    assert [item["period_start"] for item in body["items"]] == ["2026-09-28"]


async def test_customers_cannot_read_payouts(client: AsyncClient) -> None:
    response = await client.get("/api/payments/seller/payouts/", headers=user_headers(uuid4()))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_payouts_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/payments/seller/payouts/")).status_code == 401
