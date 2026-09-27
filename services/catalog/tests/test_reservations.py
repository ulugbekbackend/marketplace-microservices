"""Stock reservation: all-or-nothing, idempotent per order, safe under concurrency."""

import threading
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from contracts.enums import ProductStatus
from products import reservations
from products.models import ProductVariant, StockReservation
from products.reservations import ReservationItem, Reserved, ReserveFailed
from tests.factories import make_product, make_variant

pytestmark = pytest.mark.django_db


def _refresh(variant: ProductVariant) -> ProductVariant:
    variant.refresh_from_db()
    return variant


def test_reserve_holds_stock_and_records_the_reservation() -> None:
    first, second = make_variant(stock=10), make_variant(stock=3)
    order_id = uuid4()

    result = reservations.reserve(
        order_id, [ReservationItem(first.id, 4), ReservationItem(second.id, 3)]
    )

    assert isinstance(result, Reserved)
    assert result.status == "active"
    assert _refresh(first).reserved == 4
    assert _refresh(second).reserved == 3
    rows = StockReservation.objects.filter(order_id=order_id)
    assert {(row.variant_id, row.qty, row.status) for row in rows} == {
        (first.id, 4, "active"),
        (second.id, 3, "active"),
    }
    expected = timezone.now() + timedelta(minutes=15)
    assert abs((result.expires_at - expected).total_seconds()) < 5


def test_one_short_item_reserves_nothing() -> None:
    enough, short = make_variant(stock=10), make_variant(stock=1)

    result = reservations.reserve(
        uuid4(), [ReservationItem(enough.id, 2), ReservationItem(short.id, 2)]
    )

    assert isinstance(result, ReserveFailed)
    assert result.reason == "OUT_OF_STOCK"
    assert result.variant_ids == [short.id]
    assert _refresh(enough).reserved == 0
    assert _refresh(short).reserved == 0
    assert not StockReservation.objects.exists()


def test_every_short_variant_is_reported() -> None:
    a, b, c = make_variant(stock=0), make_variant(stock=5), make_variant(stock=1)

    result = reservations.reserve(uuid4(), [ReservationItem(v.id, 2) for v in (a, b, c)])

    assert isinstance(result, ReserveFailed)
    assert set(result.variant_ids) == {a.id, c.id}


def test_already_reserved_units_are_not_available() -> None:
    variant = make_variant(stock=5, reserved=4)

    result = reservations.reserve(uuid4(), [ReservationItem(variant.id, 2)])

    assert isinstance(result, ReserveFailed)


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(
            lambda v: ProductVariant.objects.filter(pk=v.pk).update(is_active=False),
            id="inactive-variant",
        ),
        pytest.param(
            lambda v: (
                type(v.product)
                .objects.filter(pk=v.product_id)
                .update(status=ProductStatus.ARCHIVED.value)
            ),
            id="archived-product",
        ),
    ],
)
def test_variants_not_on_sale_cannot_be_reserved(setup) -> None:  # type: ignore[no-untyped-def]
    variant = make_variant(stock=10)
    setup(variant)

    result = reservations.reserve(uuid4(), [ReservationItem(variant.id, 1)])

    assert isinstance(result, ReserveFailed)
    assert _refresh(variant).reserved == 0


def test_draft_product_cannot_be_reserved() -> None:
    variant = make_variant(product=make_product(status=ProductStatus.DRAFT.value), stock=10)

    assert isinstance(
        reservations.reserve(uuid4(), [ReservationItem(variant.id, 1)]), ReserveFailed
    )


def test_unknown_variant_fails() -> None:
    missing = uuid4()

    result = reservations.reserve(uuid4(), [ReservationItem(missing, 1)])

    assert isinstance(result, ReserveFailed)
    assert result.variant_ids == [missing]


def test_repeated_variant_lines_are_summed() -> None:
    variant = make_variant(stock=5)
    order_id = uuid4()

    result = reservations.reserve(
        order_id, [ReservationItem(variant.id, 2), ReservationItem(variant.id, 3)]
    )

    assert isinstance(result, Reserved)
    assert result.items == [ReservationItem(variant.id, 5)]
    assert _refresh(variant).reserved == 5


def test_reserving_the_same_order_twice_holds_stock_once() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    items = [ReservationItem(variant.id, 3)]

    first = reservations.reserve(order_id, items)
    second = reservations.reserve(order_id, items)

    assert isinstance(first, Reserved) and isinstance(second, Reserved)
    assert second.expires_at == first.expires_at
    assert _refresh(variant).reserved == 3
    assert StockReservation.objects.filter(order_id=order_id).count() == 1


def test_commit_takes_units_out_of_stock() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 4)])

    committed = reservations.commit(order_id)

    assert committed == [ReservationItem(variant.id, 4)]
    variant = _refresh(variant)
    assert (variant.stock, variant.reserved) == (6, 0)
    assert StockReservation.objects.get(order_id=order_id).status == "committed"


def test_commit_is_idempotent() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 4)])
    reservations.commit(order_id)

    reservations.commit(order_id)

    assert _refresh(variant).stock == 6


def test_commit_without_a_reservation_fails() -> None:
    with pytest.raises(reservations.NotReserved):
        reservations.commit(uuid4())


def test_commit_after_release_fails() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 1)])
    reservations.release(order_id)

    with pytest.raises(reservations.NotReserved):
        reservations.commit(order_id)


def test_release_gives_units_back_once() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 4)])

    freed = reservations.release(order_id)
    again = reservations.release(order_id)

    assert freed == [ReservationItem(variant.id, 4)]
    assert again == []
    variant = _refresh(variant)
    assert (variant.stock, variant.reserved) == (10, 0)
    assert StockReservation.objects.get(order_id=order_id).status == "released"


def test_release_does_not_touch_committed_stock() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 4)])
    reservations.commit(order_id)

    assert reservations.release(order_id) == []
    variant = _refresh(variant)
    assert (variant.stock, variant.reserved) == (6, 0)


def test_reserve_after_commit_returns_the_committed_reservation() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 4)])
    reservations.commit(order_id)

    result = reservations.reserve(order_id, [ReservationItem(variant.id, 4)])

    assert isinstance(result, Reserved)
    assert result.status == "committed"
    assert _refresh(variant).stock == 6


def test_released_order_can_reserve_again_for_a_late_payment() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 4)])
    reservations.release(order_id)

    result = reservations.reserve(order_id, [ReservationItem(variant.id, 4)])

    assert isinstance(result, Reserved)
    assert _refresh(variant).reserved == 4
    row = StockReservation.objects.get(order_id=order_id)
    assert row.status == "active"


def test_late_reserve_fails_when_stock_is_gone() -> None:
    variant = make_variant(stock=4)
    order_id = uuid4()
    reservations.reserve(order_id, [ReservationItem(variant.id, 4)])
    reservations.release(order_id)
    reservations.reserve(uuid4(), [ReservationItem(variant.id, 3)])

    result = reservations.reserve(order_id, [ReservationItem(variant.id, 4)])

    assert isinstance(result, ReserveFailed)
    assert StockReservation.objects.get(order_id=order_id).status == "released"


# --- concurrency (real Postgres, separate connections) ------------------------------------


def _run_in_threads(count: int, work) -> list[object]:  # type: ignore[no-untyped-def]
    results: list[object] = [None] * count
    barrier = threading.Barrier(count)

    def run(index: int) -> None:
        try:
            barrier.wait()
            results[index] = work(index)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


@pytest.mark.django_db(transaction=True)
def test_twenty_parallel_orders_for_five_units() -> None:
    variant = make_variant(stock=5)

    results = _run_in_threads(
        20, lambda _: reservations.reserve(uuid4(), [ReservationItem(variant.id, 1)])
    )

    assert sum(isinstance(r, Reserved) for r in results) == 5
    assert sum(isinstance(r, ReserveFailed) for r in results) == 15
    variant = _refresh(variant)
    assert (variant.stock, variant.reserved) == (5, 5)
    assert StockReservation.objects.filter(status="active").count() == 5


@pytest.mark.django_db(transaction=True)
def test_parallel_multi_item_orders_do_not_deadlock_or_oversell() -> None:
    a, b = make_variant(stock=6), make_variant(stock=6)

    def order(index: int) -> object:
        # Half the orders list the items in the opposite order.
        items = [ReservationItem(a.id, 1), ReservationItem(b.id, 1)]
        return reservations.reserve(uuid4(), items if index % 2 else items[::-1])

    results = _run_in_threads(16, order)

    assert sum(isinstance(r, Reserved) for r in results) == 6
    assert _refresh(a).reserved == 6
    assert _refresh(b).reserved == 6


@pytest.mark.django_db(transaction=True)
def test_the_same_order_reserved_concurrently_holds_stock_once() -> None:
    variant = make_variant(stock=10)
    order_id = uuid4()

    results = _run_in_threads(
        8, lambda _: reservations.reserve(order_id, [ReservationItem(variant.id, 2)])
    )

    assert all(isinstance(r, Reserved) for r in results)
    assert _refresh(variant).reserved == 2
    assert StockReservation.objects.filter(order_id=order_id).count() == 1
