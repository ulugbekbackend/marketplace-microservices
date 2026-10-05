"""Stock reservation for orders: reserve, commit (paid), release (expired or cancelled).

Reserving is one guarded UPDATE per variant, so two orders can never take the same unit:

    UPDATE variant SET reserved = reserved + qty
    WHERE id = ? AND is_active AND product is active AND stock - reserved >= qty

If any row does not match, the whole transaction rolls back and nothing is held.
Variants are updated in id order so concurrent orders lock rows in the same order
and cannot deadlock. Every operation is idempotent per ``order_id``.

The event consumers call these through ``products.stock``, which keeps search in step.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from contracts.enums import ProductStatus, ReservationStatus
from products.models import Product, ProductVariant, StockReservation

ACTIVE = ReservationStatus.ACTIVE.value
COMMITTED = ReservationStatus.COMMITTED.value
RELEASED = ReservationStatus.RELEASED.value


@dataclass(frozen=True, slots=True)
class ReservationItem:
    variant_id: UUID
    qty: int


@dataclass(frozen=True, slots=True)
class Reserved:
    order_id: UUID
    status: str  # "active" or "committed" when the order was already paid
    expires_at: datetime
    items: list[ReservationItem]


@dataclass(frozen=True, slots=True)
class ReserveFailed:
    order_id: UUID
    reason: str  # "OUT_OF_STOCK"
    variant_ids: list[UUID]


class NotReserved(Exception):
    """Commit was asked for an order that holds no stock."""


def normalize(items: Iterable[ReservationItem]) -> list[ReservationItem]:
    """Sum repeated variants and sort by id — the lock order that prevents deadlocks."""
    totals: dict[UUID, int] = defaultdict(int)
    for item in items:
        totals[item.variant_id] += item.qty
    return [ReservationItem(variant_id, totals[variant_id]) for variant_id in sorted(totals)]


def reserve(
    order_id: UUID, items: Iterable[ReservationItem], *, reserved_at: datetime | None = None
) -> Reserved | ReserveFailed:
    """Hold stock for every item, or for none of them.

    A repeated call for an order that already holds (or has used) its stock returns the
    existing reservation. An order whose reservation was released (expired) reserves again
    — the late payment path.

    ``reserved_at`` is when the reserving event occurred (see ``release``); now by default.
    """
    wanted = normalize(items)
    stamp = reserved_at or timezone.now()
    try:
        with transaction.atomic():
            existing = _lock_rows(order_id)
            if any(row.status != RELEASED for row in existing):
                _claim(existing, stamp)
                return _as_reserved(order_id, existing)
            released = {row.variant_id: row for row in existing}
            return _reserve_all(order_id, wanted, released, stamp)
    except IntegrityError:
        # A concurrent call for the same order inserted its rows first; ours rolled back.
        with transaction.atomic():
            return _as_reserved(order_id, _lock_rows(order_id))


def commit(order_id: UUID) -> list[ReservationItem]:
    """The order is paid: reserved units leave the stock for good."""
    with transaction.atomic():
        rows = _lock_rows(order_id)
        active = [row for row in rows if row.status == ACTIVE]
        if not active:
            if rows and all(row.status == COMMITTED for row in rows):
                return _items(rows)  # already committed
            raise NotReserved(str(order_id))
        for row in active:
            _apply(
                "stock = stock - %(qty)s, reserved = reserved - %(qty)s", row.variant_id, row.qty
            )
        _set_status(active, COMMITTED)
        return _items(active)


def release(order_id: UUID, *, reserved_before: datetime | None = None) -> list[ReservationItem]:
    """The order expired or was cancelled: give the units back. Returns what was freed.

    With ``reserved_before`` (the occurred_at of the releasing event) only rows reserved
    no later than that are freed: a late or retried ``order.expired`` must not free the
    stock a late payment reserved again after the expiry.
    """
    with transaction.atomic():
        active = [
            row
            for row in _lock_rows(order_id)
            if row.status == ACTIVE and _reserved_by(row, reserved_before)
        ]
        for row in active:
            _apply("reserved = reserved - %(qty)s", row.variant_id, row.qty)
        _set_status(active, RELEASED)
        return _items(active)


# --- internals ---------------------------------------------------------------------------


def _claim(rows: list[StockReservation], reserved_at: datetime) -> None:
    """A later reserving event found the hold still active (a late payment processed
    before the expiry it raced with): the hold now belongs to that event, so the older
    ``order.expired`` no longer frees it. ``expires_at`` stays as it is."""
    stale = [
        row.pk
        for row in rows
        if row.status == ACTIVE and (row.reserved_at is None or row.reserved_at < reserved_at)
    ]
    if stale:
        StockReservation.objects.filter(pk__in=stale).update(
            reserved_at=reserved_at, updated_at=timezone.now()
        )


def _reserved_by(row: StockReservation, cutoff: datetime | None) -> bool:
    return cutoff is None or row.reserved_at is None or row.reserved_at <= cutoff


def _reserve_all(
    order_id: UUID,
    wanted: list[ReservationItem],
    released: dict[UUID, StockReservation],
    reserved_at: datetime,
) -> Reserved | ReserveFailed:
    short = [item.variant_id for item in wanted if not _take(item)]
    if short:
        transaction.set_rollback(True)
        return ReserveFailed(order_id, "OUT_OF_STOCK", short)

    expires_at = timezone.now() + timedelta(seconds=settings.RESERVATION_TTL_SECONDS)
    for item in wanted:
        row = released.pop(item.variant_id, None)
        if row is None:
            StockReservation.objects.create(
                order_id=order_id,
                variant_id=item.variant_id,
                qty=item.qty,
                status=ACTIVE,
                expires_at=expires_at,
                reserved_at=reserved_at,
            )
        else:
            row.qty, row.status, row.expires_at = item.qty, ACTIVE, expires_at
            row.reserved_at = reserved_at
            row.save(update_fields=["qty", "status", "expires_at", "reserved_at", "updated_at"])
    return Reserved(order_id, ACTIVE, expires_at, wanted)


def _take(item: ReservationItem) -> bool:
    """The guarded UPDATE: True when the variant is on sale and had enough free units.

    All items are tried even after a failure so the answer lists every short variant.
    """
    variant_table = ProductVariant._meta.db_table
    product_table = Product._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {variant_table} AS v
               SET reserved = v.reserved + %(qty)s, updated_at = now()
              FROM {product_table} AS p
             WHERE v.id = %(id)s
               AND p.id = v.product_id
               AND p.status = %(active)s
               AND v.is_active
               AND v.stock - v.reserved >= %(qty)s
            """,
            {"id": item.variant_id, "qty": item.qty, "active": ProductStatus.ACTIVE.value},
        )
        return bool(cursor.rowcount == 1)


def _apply(assignment: str, variant_id: UUID, qty: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {ProductVariant._meta.db_table} "
            f"SET {assignment}, updated_at = now() WHERE id = %(id)s",
            {"id": variant_id, "qty": qty},
        )


def _lock_rows(order_id: UUID) -> list[StockReservation]:
    return list(
        StockReservation.objects.select_for_update()
        .filter(order_id=order_id)
        .order_by("variant_id")
    )


def _set_status(rows: list[StockReservation], status: str) -> None:
    StockReservation.objects.filter(pk__in=[row.pk for row in rows]).update(
        status=status, updated_at=timezone.now()
    )


def _items(rows: Iterable[StockReservation]) -> list[ReservationItem]:
    return [ReservationItem(row.variant_id, row.qty) for row in rows]


def _as_reserved(order_id: UUID, rows: list[StockReservation]) -> Reserved:
    held = [row for row in rows if row.status != RELEASED]
    status = COMMITTED if all(row.status == COMMITTED for row in held) else ACTIVE
    return Reserved(order_id, status, max(row.expires_at for row in held), _items(held))
