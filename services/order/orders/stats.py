"""Seller dashboard numbers. Days, weeks and months follow Tashkent time; the DB stays UTC.

Cancelled sub-orders are left out of the sums (they earn nothing) but still show up in
the per-status counts. Aggregation happens in the database, per Tashkent day.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from contracts.enums import SubOrderStatus
from orders.models import SubOrder

TASHKENT = ZoneInfo("Asia/Tashkent")
DAILY_DAYS = 30


@dataclass(frozen=True, slots=True)
class Totals:
    orders: int = 0
    gross_tiyin: int = 0
    net_tiyin: int = 0

    def __add__(self, other: "Totals") -> "Totals":
        return Totals(
            self.orders + other.orders,
            self.gross_tiyin + other.gross_tiyin,
            self.net_tiyin + other.net_tiyin,
        )

    def as_dict(self) -> dict[str, int]:
        return {"orders": self.orders, "gross_tiyin": self.gross_tiyin, "net_tiyin": self.net_tiyin}


def local_today(now: datetime | None = None) -> date:
    return (now or timezone.now()).astimezone(TASHKENT).date()


def day_start(day: date) -> datetime:
    """The UTC instant a Tashkent calendar day begins."""
    return datetime.combine(day, time.min, tzinfo=TASHKENT)


def seller_stats(seller_id: UUID, *, now: datetime | None = None) -> dict[str, Any]:
    today = local_today(now)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    daily_start = today - timedelta(days=DAILY_DAYS - 1)
    first_day = min(week_start, month_start, daily_start)

    per_day = _totals_per_day(seller_id, first_day, today)

    def between(start: date) -> Totals:
        return sum((t for day, t in per_day.items() if start <= day <= today), Totals())

    daily = []
    for offset in range(DAILY_DAYS):
        day = daily_start + timedelta(days=offset)
        daily.append({"date": day, **per_day.get(day, Totals()).as_dict()})

    return {
        "today": between(today).as_dict(),
        "week": between(week_start).as_dict(),
        "month": between(month_start).as_dict(),
        "daily": daily,
        "by_status": _count_by_status(seller_id),
    }


def _totals_per_day(seller_id: UUID, first_day: date, last_day: date) -> dict[date, Totals]:
    rows = (
        SubOrder.objects.filter(
            seller_id=seller_id,
            created_at__gte=day_start(first_day),
            created_at__lt=day_start(last_day + timedelta(days=1)),
        )
        .exclude(status=SubOrderStatus.CANCELLED_BY_SELLER.value)
        .annotate(day=TruncDate("created_at", tzinfo=TASHKENT))
        .values("day")
        .annotate(
            orders=Count("id"),
            gross=Sum("subtotal_tiyin"),
            commission=Sum("commission_tiyin"),
        )
        .order_by("day")
    )
    return {
        row["day"]: Totals(
            orders=int(row["orders"]),
            gross_tiyin=int(row["gross"]),
            net_tiyin=int(row["gross"]) - int(row["commission"]),
        )
        for row in rows
    }


def _count_by_status(seller_id: UUID) -> dict[str, int]:
    counts = {status.value: 0 for status in SubOrderStatus}
    rows = (
        SubOrder.objects.filter(seller_id=seller_id)
        .values("status")
        .annotate(n=Count("id"))
        .order_by()
    )
    for row in rows:
        counts[row["status"]] = int(row["n"])
    return counts
