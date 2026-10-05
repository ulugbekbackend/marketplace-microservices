"""Reservation operations that keep search in step with availability.

``products.reservations`` moves units between free, reserved and sold. When that flips an
active product between "in stock" and "sold out", search has to hear about it: these
wrappers write ``product.updated`` for exactly the flipped products, in the same
transaction as the stock change.

The products involved are locked first, in id order, the same order the seller services
lock a product before its variants. Every writer of a product's stock holds that lock,
so the before/after comparison cannot miss a concurrent change.
"""

from collections.abc import Callable, Collection, Iterable
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from contracts.enums import ProductStatus
from products import reservations
from products.documents import record_product_change
from products.models import Product, ProductVariant, StockReservation
from products.reservations import ReservationItem, Reserved, ReserveFailed


def reserve(
    order_id: UUID,
    items: Iterable[ReservationItem],
    *,
    reserved_at: datetime | None = None,
    correlation_id: UUID | None = None,
) -> Reserved | ReserveFailed:
    wanted = list(items)
    product_ids = set(
        ProductVariant.objects.filter(id__in=[item.variant_id for item in wanted]).values_list(
            "product_id", flat=True
        )
    )
    return _watching(
        product_ids,
        lambda: reservations.reserve(order_id, wanted, reserved_at=reserved_at),
        correlation_id,
    )


def commit(order_id: UUID, *, correlation_id: UUID | None = None) -> list[ReservationItem]:
    """Raises ``reservations.NotReserved`` like the underlying commit."""
    return _watching(
        _order_products(order_id), lambda: reservations.commit(order_id), correlation_id
    )


def release(
    order_id: UUID,
    *,
    reserved_before: datetime | None = None,
    correlation_id: UUID | None = None,
) -> list[ReservationItem]:
    return _watching(
        _order_products(order_id),
        lambda: reservations.release(order_id, reserved_before=reserved_before),
        correlation_id,
    )


def release_stale(*, grace: timedelta, limit: int = 100) -> int:
    """Release active reservations that expired more than ``grace`` ago.

    The order service releases expired orders through ``order.expired``; this sweep only
    covers a lost event. Returns how many orders were released.
    """
    cutoff = timezone.now() - grace
    order_ids = list(
        StockReservation.objects.filter(status=reservations.ACTIVE, expires_at__lt=cutoff)
        .values_list("order_id", flat=True)
        .order_by("order_id")
        .distinct()[:limit]
    )
    released = 0
    for order_id in order_ids:
        if _release_if_still_stale(order_id, cutoff):
            released += 1
    return released


# --- internals ---------------------------------------------------------------------------


def _release_if_still_stale(order_id: UUID, cutoff: datetime) -> bool:
    def run() -> bool:
        # Another sweeper may hold these rows, or a late payment may have reserved the
        # order again meanwhile: re-check under the lock and leave it alone if so.
        still_stale = list(
            StockReservation.objects.select_for_update(skip_locked=True).filter(
                order_id=order_id, status=reservations.ACTIVE, expires_at__lt=cutoff
            )
        )
        if not still_stale:
            return False
        return bool(reservations.release(order_id))

    return _watching(_order_products(order_id), run, None)


def _order_products(order_id: UUID) -> set[UUID]:
    return set(
        StockReservation.objects.filter(order_id=order_id).values_list(
            "variant__product_id", flat=True
        )
    )


def _in_stock(product_ids: Collection[UUID]) -> set[UUID]:
    return set(
        ProductVariant.objects.filter(
            product_id__in=product_ids,
            product__status=ProductStatus.ACTIVE.value,
            is_active=True,
            stock__gt=F("reserved"),
        )
        .values_list("product_id", flat=True)
        .distinct()
    )


def _watching[T](
    product_ids: set[UUID], operation: Callable[[], T], correlation_id: UUID | None
) -> T:
    with transaction.atomic():
        if not product_ids:
            return operation()
        products = list(
            Product.objects.select_for_update(of=("self",))
            .select_related("seller", "category")
            .filter(id__in=product_ids)
            .order_by("id")
        )
        # Only active products count, so only they can flip.
        before = _in_stock(product_ids)
        result = operation()
        flipped = before ^ _in_stock(product_ids)
        for product in products:
            if product.id in flipped:
                # A change of availability is a change of the product (as for seller edits).
                product.save(update_fields=["updated_at"])
                record_product_change(product, correlation_id=correlation_id)
        return result
