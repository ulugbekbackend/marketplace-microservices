"""Seller stats: Tashkent day/week/month boundaries, cancelled sub-orders, zero-filled days."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from contracts.enums import SubOrderStatus, UserRole
from orders.stats import seller_stats
from tests.conftest import user_client
from tests.factories import make_sub_order

pytestmark = pytest.mark.django_db

# Tuesday 10 March 2026, 10:00 in Tashkent (UTC+5).
NOW = datetime(2026, 3, 10, 5, 0, tzinfo=UTC)
TODAY_STARTS = datetime(2026, 3, 9, 19, 0, tzinfo=UTC)
WEEK_STARTS = datetime(2026, 3, 8, 19, 0, tzinfo=UTC)  # Monday 9 March, Tashkent
MONTH_STARTS = datetime(2026, 2, 28, 19, 0, tzinfo=UTC)  # 1 March, Tashkent
SECOND = timedelta(seconds=1)


def totals(orders: int, gross: int) -> dict[str, int]:
    """Every test sub-order uses a 10% commission."""
    return {"orders": orders, "gross_tiyin": gross, "net_tiyin": gross - gross // 10}


@pytest.fixture
def seller_id() -> UUID:
    return uuid4()


def sale(
    seller_id: UUID,
    at: datetime | None,
    amount: int = 1_000_000,
    status: SubOrderStatus = SubOrderStatus.NEW,
) -> None:
    make_sub_order(seller_id, subtotal_tiyin=amount, created_at=at, status=status)


def test_boundaries_follow_tashkent_midnight(seller_id: UUID) -> None:
    assert NOW.date().weekday() == 1  # a Tuesday
    sale(seller_id, TODAY_STARTS, 100_000)  # first second of today
    sale(seller_id, TODAY_STARTS - SECOND, 200_000)  # yesterday, Monday
    sale(seller_id, WEEK_STARTS, 400_000)  # Monday's first second
    sale(seller_id, WEEK_STARTS - SECOND, 800_000)  # Sunday: last week, this month
    sale(seller_id, MONTH_STARTS, 1_600_000)  # 1 March
    sale(seller_id, MONTH_STARTS - SECOND, 3_200_000)  # 28 February: only in daily

    stats = seller_stats(seller_id, now=NOW)

    assert stats["today"] == totals(1, 100_000)
    assert stats["week"] == totals(3, 700_000)
    assert stats["month"] == totals(5, 3_100_000)
    by_day = {row["date"]: row for row in stats["daily"]}
    assert by_day[date(2026, 3, 10)]["gross_tiyin"] == 100_000
    assert by_day[date(2026, 3, 9)]["gross_tiyin"] == 600_000
    assert by_day[date(2026, 3, 8)]["gross_tiyin"] == 800_000
    assert by_day[date(2026, 3, 1)]["gross_tiyin"] == 1_600_000
    assert by_day[date(2026, 2, 28)] == {"date": date(2026, 2, 28), **totals(1, 3_200_000)}


def test_daily_has_thirty_zero_filled_days_oldest_first(seller_id: UUID) -> None:
    sale(seller_id, NOW - timedelta(days=29))  # 9 Feb, the first day shown
    sale(seller_id, NOW - timedelta(days=30))  # 8 Feb, not shown

    daily = seller_stats(seller_id, now=NOW)["daily"]

    assert len(daily) == 30
    assert [row["date"] for row in daily] == [
        date(2026, 2, 9) + timedelta(days=n) for n in range(30)
    ]
    assert daily[0] == {"date": date(2026, 2, 9), **totals(1, 1_000_000)}
    assert all(row == {"date": row["date"], **totals(0, 0)} for row in daily[1:])


def test_month_reaches_further_back_than_daily(seller_id: UUID) -> None:
    end_of_march = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
    sale(seller_id, MONTH_STARTS)  # 1 March: in the month, before the 30 days

    stats = seller_stats(seller_id, now=end_of_march)

    assert stats["month"] == totals(1, 1_000_000)
    assert stats["daily"][0]["date"] == date(2026, 3, 2)
    assert sum(row["orders"] for row in stats["daily"]) == 0


def test_cancelled_is_counted_by_status_only(seller_id: UUID) -> None:
    sale(seller_id, NOW - SECOND, 500_000)
    sale(seller_id, NOW - SECOND, 700_000, status=SubOrderStatus.CANCELLED_BY_SELLER)
    sale(seller_id, NOW - SECOND, 300_000, status=SubOrderStatus.ACCEPTED)
    sale(seller_id, NOW - timedelta(days=400), 100, status=SubOrderStatus.ACCEPTED)

    stats = seller_stats(seller_id, now=NOW)

    assert stats["today"] == totals(2, 800_000)
    assert stats["by_status"] == {
        "NEW": 1,
        "ACCEPTED": 2,
        "SHIPPED": 0,
        "DELIVERED": 0,
        "CANCELLED_BY_SELLER": 1,
    }


def test_net_uses_the_stored_commission(seller_id: UUID) -> None:
    make_sub_order(seller_id, subtotal_tiyin=333_336, rate="0.0850", created_at=NOW - SECOND)

    stats = seller_stats(seller_id, now=NOW)

    assert stats["today"] == {"orders": 1, "gross_tiyin": 333_336, "net_tiyin": 305_002}


def test_only_own_sub_orders_count(seller_id: UUID, django_assert_num_queries: Any) -> None:
    sale(uuid4(), NOW - SECOND)

    with django_assert_num_queries(2):  # per-day sums + per-status counts
        stats = seller_stats(seller_id, now=NOW)

    assert stats["today"] == totals(0, 0)
    assert set(stats["by_status"].values()) == {0}


def test_endpoint_shape(seller_id: UUID) -> None:
    sale(seller_id, None, 250_000)  # created now
    sale(uuid4(), None)

    response = user_client(seller_id, UserRole.SELLER).get("/api/orders/seller/stats/")

    assert response.status_code == 200
    body = response.json()
    assert body["today"] == totals(1, 250_000)
    assert body["week"]["orders"] >= 1
    assert body["month"]["orders"] >= 1
    assert len(body["daily"]) == 30
    assert body["daily"][-1]["orders"] == 1
    date.fromisoformat(body["daily"][-1]["date"])
    assert body["by_status"]["NEW"] == 1
