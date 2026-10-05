"""Event handlers of catalog.q: reservations driven by the order saga, search kept in step."""

import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.db import connection
from pydantic import ValidationError

from contracts.enums import EventType, ProductStatus
from contracts.events import (
    EventEnvelope,
    Frozen,
    OrderCancelled,
    OrderCreated,
    OrderExpired,
    OrderItemRef,
    OrderPaid,
    ProductUpdated,
    SellerApproved,
    StockFailed,
    StockReserved,
    SubOrderRef,
    build_event,
)
from contracts.topology import CONSUMER_BINDINGS
from messaging.handlers import HANDLERS
from messaging.models import Outbox, ProcessedEvent
from messaging.outbox import to_envelope
from products.models import ProductVariant, StockReservation
from py_common.rabbit import PermanentError, make_dispatch
from sellers.models import Seller
from tests.factories import make_product, make_variant

pytestmark = pytest.mark.django_db

dispatch = make_dispatch(HANDLERS)


def event(
    payload: Frozen, *, correlation_id: UUID | None = None, at: datetime | None = None
) -> EventEnvelope:
    return build_event(
        payload,
        producer="order",
        correlation_id=correlation_id or uuid4(),
        occurred_at=at or datetime.now(UTC),
    )


def deliver(envelope: EventEnvelope) -> None:
    dispatch(envelope.model_dump_json().encode())


def created(
    order_id: UUID,
    *items: tuple[ProductVariant, int],
    retry: bool = False,
    at: datetime | None = None,
) -> EventEnvelope:
    return event(
        OrderCreated(
            order_id=order_id,
            items=[OrderItemRef(variant_id=variant.id, qty=qty) for variant, qty in items],
            reserve_retry=retry,
        ),
        at=at,
    )


def paid(order_id: UUID, variant: ProductVariant) -> EventEnvelope:
    return event(
        OrderPaid(
            order_id=order_id,
            customer_id=uuid4(),
            sub_orders=[
                SubOrderRef(
                    id=uuid4(),
                    seller_id=variant.product.seller_id,
                    items=[OrderItemRef(variant_id=variant.id, qty=1)],
                    subtotal_tiyin=variant.price_tiyin,
                    commission_tiyin=0,
                )
            ],
        )
    )


def expired(
    order_id: UUID, variant: ProductVariant, *, at: datetime | None = None
) -> EventEnvelope:
    return event(
        OrderExpired(order_id=order_id, items=[OrderItemRef(variant_id=variant.id, qty=1)]),
        at=at,
    )


def cancelled(
    order_id: UUID, variant: ProductVariant, *, at: datetime | None = None
) -> EventEnvelope:
    return event(
        OrderCancelled(
            order_id=order_id,
            items=[OrderItemRef(variant_id=variant.id, qty=1)],
            reason="customer",
        ),
        at=at,
    )


def outbox(event_type: EventType) -> list[EventEnvelope]:
    return [to_envelope(row) for row in Outbox.objects.filter(event_type=event_type.value)]


def counts(variant: ProductVariant) -> tuple[int, int]:
    variant.refresh_from_db()
    return variant.stock, variant.reserved


# --- order.created ------------------------------------------------------------------------


def test_order_created_reserves_and_reports_stock_reserved() -> None:
    variant = make_variant(stock=5)
    order_id = uuid4()
    envelope = created(order_id, (variant, 2))

    deliver(envelope)

    assert counts(variant) == (5, 2)
    [reply] = outbox(EventType.STOCK_RESERVED)
    assert reply.producer == "catalog"
    assert reply.correlation_id == envelope.correlation_id
    payload = StockReserved.model_validate(reply.payload)
    assert payload.order_id == order_id
    assert payload.expires_at == StockReservation.objects.get(order_id=order_id).expires_at
    assert ProcessedEvent.objects.filter(event_id=envelope.event_id).exists()
    assert outbox(EventType.PRODUCT_UPDATED) == []  # still in stock: search needs nothing


def test_duplicate_order_created_has_no_effect() -> None:
    variant = make_variant(stock=5)
    envelope = created(uuid4(), (variant, 2))

    deliver(envelope)
    deliver(envelope)

    assert counts(variant) == (5, 2)
    assert len(outbox(EventType.STOCK_RESERVED)) == 1


def test_out_of_stock_reports_stock_failed_with_the_short_variants() -> None:
    enough, short = make_variant(stock=5), make_variant(stock=1)
    order_id = uuid4()
    envelope = created(order_id, (enough, 1), (short, 2))

    deliver(envelope)

    assert counts(enough) == (5, 0)
    assert counts(short) == (1, 0)
    assert not StockReservation.objects.exists()
    [reply] = outbox(EventType.STOCK_FAILED)
    assert reply.correlation_id == envelope.correlation_id
    assert StockFailed.model_validate(reply.payload) == StockFailed(
        order_id=order_id, reason="OUT_OF_STOCK", variant_ids=[short.id]
    )
    assert outbox(EventType.STOCK_RESERVED) == []


@pytest.mark.django_db(transaction=True)
def test_stock_failed_commits_with_the_processed_row_while_the_hold_rolls_back() -> None:
    """reserve() rolls back its own savepoint on failure; the handler's writes survive."""
    enough, short = make_variant(stock=5), make_variant(stock=0)
    envelope = created(uuid4(), (enough, 1), (short, 1))

    deliver(envelope)

    # Read on a fresh connection: only committed data is visible there.
    seen: dict[str, object] = {}

    def look() -> None:
        try:
            seen["processed"] = ProcessedEvent.objects.filter(event_id=envelope.event_id).exists()
            seen["failed"] = Outbox.objects.filter(event_type="stock.failed").count()
            seen["reserved"] = ProductVariant.objects.get(id=enough.id).reserved
            seen["holds"] = StockReservation.objects.count()
        finally:
            connection.close()

    thread = threading.Thread(target=look)
    thread.start()
    thread.join()
    assert seen == {"processed": True, "failed": 1, "reserved": 0, "holds": 0}

    deliver(envelope)  # a redelivery after the commit is skipped
    assert Outbox.objects.filter(event_type="stock.failed").count() == 1


def test_reserve_retry_holds_the_stock_again_after_expiry() -> None:
    variant = make_variant(stock=3)
    order_id = uuid4()
    deliver(created(order_id, (variant, 2)))
    deliver(expired(order_id, variant))
    assert counts(variant) == (3, 0)

    deliver(created(order_id, (variant, 2), retry=True))

    assert counts(variant) == (3, 2)
    assert StockReservation.objects.get(order_id=order_id).status == "active"
    assert len(outbox(EventType.STOCK_RESERVED)) == 2


def test_reserve_retry_without_stock_reports_failure() -> None:
    variant = make_variant(stock=2)
    order_id = uuid4()
    deliver(created(order_id, (variant, 2)))
    deliver(expired(order_id, variant))
    deliver(created(uuid4(), (variant, 2)))  # someone else took the units meanwhile

    deliver(created(order_id, (variant, 2), retry=True))

    [reply] = outbox(EventType.STOCK_FAILED)
    assert StockFailed.model_validate(reply.payload).order_id == order_id


def test_unknown_variant_fails_the_reservation() -> None:
    missing = uuid4()
    envelope = event(
        OrderCreated(order_id=uuid4(), items=[OrderItemRef(variant_id=missing, qty=1)])
    )

    deliver(envelope)

    [reply] = outbox(EventType.STOCK_FAILED)
    assert StockFailed.model_validate(reply.payload).variant_ids == [missing]


# --- order.paid / expired / cancelled ------------------------------------------------------


def test_order_paid_commits_the_reservation_once() -> None:
    variant = make_variant(stock=5)
    order_id = uuid4()
    deliver(created(order_id, (variant, 2)))
    envelope = paid(order_id, variant)

    deliver(envelope)
    deliver(envelope)

    assert counts(variant) == (3, 0)
    assert StockReservation.objects.get(order_id=order_id).status == "committed"
    assert outbox(EventType.PRODUCT_UPDATED) == []  # committing does not change availability


def test_order_paid_without_a_reservation_is_a_permanent_error() -> None:
    envelope = paid(uuid4(), make_variant())

    with pytest.raises(PermanentError, match="holds no stock"):
        deliver(envelope)

    # Nothing is recorded, so a replay from the DLQ can still be applied.
    assert not ProcessedEvent.objects.filter(event_id=envelope.event_id).exists()


@pytest.mark.parametrize("make_event", [expired, cancelled])
def test_expired_or_cancelled_order_gives_the_units_back(make_event) -> None:  # type: ignore[no-untyped-def]
    variant = make_variant(stock=5)
    order_id = uuid4()
    deliver(created(order_id, (variant, 2)))
    envelope = make_event(order_id, variant)

    deliver(envelope)
    deliver(created(uuid4(), (variant, 4)))  # the freed units can be sold again
    deliver(envelope)  # duplicate: the other order's hold stays

    assert counts(variant) == (5, 4)
    assert StockReservation.objects.get(order_id=order_id).status == "released"


def test_release_of_an_unknown_order_is_a_no_op() -> None:
    envelope = expired(uuid4(), make_variant())

    deliver(envelope)

    assert ProcessedEvent.objects.filter(event_id=envelope.event_id).exists()
    assert not Outbox.objects.exists()


# --- late payment vs. a late expiry ------------------------------------------------------

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_expiry_processed_after_the_re_reservation_frees_nothing() -> None:
    """order.expired sat in the retry queue while the late payment re-reserved the order."""
    variant = make_variant(stock=3)
    order_id = uuid4()
    deliver(created(order_id, (variant, 2), at=T0))
    first_expiry = expired(order_id, variant, at=T0 + timedelta(minutes=15))
    deliver(first_expiry)
    deliver(created(order_id, (variant, 2), retry=True, at=T0 + timedelta(minutes=16)))
    # A second order.expired copy (redelivered under a new id, or a retried one) arrives late.
    late_expiry = expired(order_id, variant, at=T0 + timedelta(minutes=15))

    deliver(late_expiry)

    assert counts(variant) == (3, 2)
    assert StockReservation.objects.get(order_id=order_id).status == "active"
    assert ProcessedEvent.objects.filter(event_id=late_expiry.event_id).exists()

    deliver(paid(order_id, variant))

    assert counts(variant) == (1, 0)
    assert StockReservation.objects.get(order_id=order_id).status == "committed"


def test_retry_processed_before_the_expiry_keeps_the_hold() -> None:
    """The retry overtook the expiry: it finds the hold still active and claims it."""
    variant = make_variant(stock=3)
    order_id = uuid4()
    deliver(created(order_id, (variant, 2), at=T0))
    original = StockReservation.objects.get(order_id=order_id)
    deliver(created(order_id, (variant, 2), retry=True, at=T0 + timedelta(minutes=16)))

    deliver(expired(order_id, variant, at=T0 + timedelta(minutes=15)))

    hold = StockReservation.objects.get(order_id=order_id)
    assert (hold.status, hold.reserved_at) == ("active", T0 + timedelta(minutes=16))
    assert hold.expires_at == original.expires_at  # a repeat reserve does not extend
    assert counts(variant) == (3, 2)
    assert len(outbox(EventType.STOCK_RESERVED)) == 2

    deliver(paid(order_id, variant))

    assert counts(variant) == (1, 0)


def test_expiry_releases_a_hold_reserved_before_it() -> None:
    variant = make_variant(stock=3)
    order_id = uuid4()
    deliver(created(order_id, (variant, 2), at=T0))

    deliver(expired(order_id, variant, at=T0 + timedelta(minutes=15)))

    assert counts(variant) == (3, 0)
    hold = StockReservation.objects.get(order_id=order_id)
    assert (hold.status, hold.reserved_at) == ("released", T0)


def test_expiry_at_the_same_instant_still_releases() -> None:
    variant = make_variant(stock=3)
    order_id = uuid4()
    deliver(created(order_id, (variant, 1), at=T0))

    deliver(cancelled(order_id, variant, at=T0))

    assert counts(variant) == (3, 0)


def test_rows_from_before_the_column_existed_are_released() -> None:
    variant = make_variant(stock=3)
    order_id = uuid4()
    deliver(created(order_id, (variant, 1), at=T0))
    StockReservation.objects.filter(order_id=order_id).update(reserved_at=None)

    deliver(expired(order_id, variant, at=T0 - timedelta(days=1)))

    assert counts(variant) == (3, 0)


# --- search in step -----------------------------------------------------------------------


def test_reserving_the_last_units_marks_the_product_sold_out() -> None:
    variant = make_variant(stock=2)
    envelope = created(uuid4(), (variant, 2))

    deliver(envelope)

    [update] = outbox(EventType.PRODUCT_UPDATED)
    assert update.correlation_id == envelope.correlation_id
    document = ProductUpdated.model_validate(update.payload)
    assert document.product_id == variant.product_id
    assert document.in_stock is False


def test_releasing_a_sold_out_product_marks_it_in_stock_again() -> None:
    variant = make_variant(stock=1)
    order_id = uuid4()
    deliver(created(order_id, (variant, 1)))

    deliver(cancelled(order_id, variant))

    first, second = (
        ProductUpdated.model_validate(row.payload) for row in outbox(EventType.PRODUCT_UPDATED)
    )
    assert first.in_stock is False
    assert second.in_stock is True
    # Availability is a change of the product: the newer document carries a newer stamp.
    assert variant.product.updated_at < first.updated_at < second.updated_at


def test_another_variant_in_stock_keeps_the_product_available() -> None:
    product = make_product()
    last = make_variant(product=product, stock=1)
    make_variant(product=product, stock=3)

    deliver(created(uuid4(), (last, 1)))

    assert outbox(EventType.PRODUCT_UPDATED) == []


def test_only_flipped_products_are_reindexed() -> None:
    sold_out = make_variant(stock=1)
    plenty = make_variant(stock=9)

    deliver(created(uuid4(), (sold_out, 1), (plenty, 1)))

    [update] = outbox(EventType.PRODUCT_UPDATED)
    assert ProductUpdated.model_validate(update.payload).product_id == sold_out.product_id


def test_products_off_sale_are_not_reindexed() -> None:
    variant = make_variant(stock=1)
    order_id = uuid4()
    deliver(created(order_id, (variant, 1)))
    Outbox.objects.all().delete()
    variant.product.status = ProductStatus.ARCHIVED.value
    variant.product.save(update_fields=["status"])

    deliver(expired(order_id, variant))

    assert counts(variant) == (1, 0)
    assert outbox(EventType.PRODUCT_UPDATED) == []
    assert outbox(EventType.PRODUCT_DELETED) == []


@pytest.mark.django_db(transaction=True)
def test_two_orders_racing_for_the_last_unit() -> None:
    variant = make_variant(stock=1)
    envelopes = [created(uuid4(), (variant, 1)) for _ in range(2)]
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def run(envelope: EventEnvelope) -> None:
        try:
            barrier.wait()
            deliver(envelope)
        except BaseException as exc:  # pragma: no cover - only on failure
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(envelope,)) for envelope in envelopes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert counts(variant) == (1, 1)
    assert len(outbox(EventType.STOCK_RESERVED)) == 1
    assert len(outbox(EventType.STOCK_FAILED)) == 1
    [update] = outbox(EventType.PRODUCT_UPDATED)
    assert ProductUpdated.model_validate(update.payload).in_stock is False


# --- dispatch wiring ----------------------------------------------------------------------


def test_seller_approved_creates_the_shop() -> None:
    user_id = uuid4()

    deliver(event(SellerApproved(user_id=user_id, shop_name="Bukhara Silk")))

    seller = Seller.objects.get(id=user_id)
    assert seller.shop_name == "Bukhara Silk"
    assert seller.is_verified
    assert seller.commission_rate == Decimal("0.1000")


def test_handlers_cover_the_catalog_bindings() -> None:
    assert set(HANDLERS) == set(CONSUMER_BINDINGS["catalog"])


def test_events_without_a_handler_are_ignored() -> None:
    deliver(event(StockFailed(order_id=uuid4(), reason="x")))

    assert not ProcessedEvent.objects.exists()


def test_malformed_payload_is_rejected() -> None:
    envelope = created(uuid4(), (make_variant(), 1))
    envelope.payload["items"] = []

    with pytest.raises(ValidationError):
        deliver(envelope)
    assert not ProcessedEvent.objects.exists()
