"""The checkout saga: catalog and payment events fed into the order handlers."""

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.utils import timezone
from pydantic import ValidationError
from rest_framework.test import APIClient

from contracts.enums import EventType, OrderStatus, PaymentProvider, SubOrderStatus
from contracts.events import (
    EventEnvelope,
    OrderCancelled,
    OrderCreated,
    OrderExpired,
    OrderPaid,
    OrderRefundRequested,
    PaymentPaid,
    PaymentRefunded,
    StockFailed,
    StockReserved,
)
from contracts.topology import CONSUMER_BINDINGS
from messaging.models import Outbox, ProcessedEvent
from orders import saga, services
from orders.clients import ServiceUnavailable
from orders.management.commands.consume_events import make_handler
from orders.models import Order, OrderStatusHistory, SubOrder
from orders.saga import HANDLERS, NotReserved, StaleOrder
from py_common.rabbit import PermanentError
from tests.conftest import FakeUpstream, checkout, incoming, known_variants, outbox
from tests.factories import make_order, make_paid_order

pytestmark = pytest.mark.django_db

S = OrderStatus


def stock_reserved(order: Order, *, minutes: int = 15) -> EventEnvelope:
    return incoming(
        StockReserved(order_id=order.id, expires_at=timezone.now() + timedelta(minutes=minutes))
    )


def stock_failed(order: Order, reason: str = "OUT_OF_STOCK") -> EventEnvelope:
    return incoming(StockFailed(order_id=order.id, reason=reason, variant_ids=[uuid4()]))


def payment_paid(order: Order, amount: int | None = None) -> EventEnvelope:
    return incoming(
        PaymentPaid(
            order_id=order.id,
            transaction_id=uuid4(),
            amount_tiyin=order.total_tiyin if amount is None else amount,
            provider=PaymentProvider.PAYME,
        ),
        producer="payment",
    )


def payment_refunded(order: Order, amount: int | None = None) -> EventEnvelope:
    return incoming(
        PaymentRefunded(
            order_id=order.id, amount_tiyin=order.total_tiyin if amount is None else amount
        ),
        producer="payment",
    )


def statuses(order: Order) -> list[tuple[str | None, str, str]]:
    return list(
        OrderStatusHistory.objects.filter(order=order).values_list(
            "from_status", "to_status", "reason"
        )
    )


def reload(order: Order) -> Order:
    return Order.objects.get(id=order.id)


# --- stock.reserved / stock.failed --------------------------------------------------------


def test_stock_reserved_moves_pending_to_reserved() -> None:
    order = make_order(status=S.PENDING)
    event = stock_reserved(order)

    saga.on_stock_reserved(event)

    order = reload(order)
    assert order.status == S.RESERVED.value
    assert order.reserved_until == StockReserved.model_validate(event.payload).expires_at
    assert statuses(order)[-1] == ("PENDING", "RESERVED", "")
    assert ProcessedEvent.objects.filter(event_id=event.event_id).exists()
    assert not Outbox.objects.exists()


def test_duplicate_stock_reserved_changes_nothing() -> None:
    order = make_order(status=S.PENDING)
    event = stock_reserved(order)
    saga.on_stock_reserved(event)
    before = reload(order).updated_at

    saga.on_stock_reserved(event)

    assert reload(order).updated_at == before
    assert len(statuses(order)) == 2


@pytest.mark.parametrize(
    ("reason", "cancel_reason"),
    [("OUT_OF_STOCK", "OUT_OF_STOCK"), ("PRODUCT_INACTIVE", "RESERVATION_FAILED")],
)
def test_stock_failed_cancels_a_pending_order(reason: str, cancel_reason: str) -> None:
    order = make_order(status=S.PENDING)
    event = stock_failed(order, reason)

    saga.on_stock_failed(event)
    saga.on_stock_failed(event)  # duplicate delivery

    order = reload(order)
    assert order.status == S.CANCELLED.value
    assert order.cancel_reason == cancel_reason
    assert order.reserved_until is None
    assert statuses(order)[-1] == ("PENDING", "CANCELLED", cancel_reason)
    [cancelled] = outbox(EventType.ORDER_CANCELLED)
    payload = OrderCancelled.model_validate(cancelled.payload)
    assert payload.reason == cancel_reason
    assert [ref.variant_id for ref in payload.items] == [i.variant_id for i in order.items.all()]


@pytest.mark.parametrize("status", [S.RESERVED, S.CANCELLED, S.EXPIRED, S.PAID])
def test_stock_failed_outside_a_reservation_is_ignored(status: OrderStatus) -> None:
    order = make_order(status=status)

    saga.on_stock_failed(stock_failed(order))

    assert reload(order).status == status.value
    assert not Outbox.objects.exists()


def test_customer_cancel_while_pending_then_stock_reserved_releases_again(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    upstream.put_in_cart(customer_id, upstream.add_variant(), 2)
    order_id = checkout(api).json()["order_id"]
    assert api.post(f"/api/orders/{order_id}/cancel/").json()["status"] == "CANCELLED"
    order = Order.objects.get(id=order_id)
    history = statuses(order)

    saga.on_stock_reserved(stock_reserved(order))

    order = reload(order)
    assert order.status == S.CANCELLED.value
    assert order.reserved_until is None
    assert statuses(order) == history
    first, again = outbox(EventType.ORDER_CANCELLED)
    assert first.payload == again.payload  # same items and reason: the catalog releases
    assert again.payload["reason"] == "CANCELLED_BY_CUSTOMER"
    assert first.event_id != again.event_id


def test_stock_reserved_for_an_expired_order_releases_again() -> None:
    order = make_order(status=S.EXPIRED)

    saga.on_stock_reserved(stock_reserved(order))

    assert reload(order).status == S.EXPIRED.value
    [expired] = outbox(EventType.ORDER_EXPIRED)
    assert OrderExpired.model_validate(expired.payload).order_id == order.id


def test_stock_reserved_after_a_refunded_late_payment_releases_again() -> None:
    order = make_order(status=S.REFUNDED, late_payment=True)

    saga.on_stock_reserved(stock_reserved(order))

    assert reload(order).status == S.REFUNDED.value
    assert len(outbox(EventType.ORDER_EXPIRED)) == 1


@pytest.mark.parametrize("status", [S.RESERVED, S.PAID, S.FULFILLING, S.REFUNDED])
def test_stock_reserved_in_other_states_is_ignored(status: OrderStatus) -> None:
    order = make_order(status=status)
    before = reload(order).reserved_until

    saga.on_stock_reserved(stock_reserved(order, minutes=60))

    order = reload(order)
    assert order.status == status.value
    assert order.reserved_until == before
    assert not Outbox.objects.exists()


# --- payment.paid ---------------------------------------------------------------------------


def test_payment_paid_pays_a_reserved_order(upstream: FakeUpstream) -> None:
    seller_a, seller_b = sorted([uuid4(), uuid4()])
    order = make_order(lines=[(seller_a, 1_000, 2), (seller_b, 500, 1)])
    known_variants(upstream, order)
    event = payment_paid(order)

    saga.on_payment_paid(event)

    order = reload(order)
    assert order.status == S.PAID.value
    assert statuses(order)[-1] == ("RESERVED", "PAID", "")
    subs = list(SubOrder.objects.filter(order=order).order_by("seller_id"))
    assert [(s.seller_id, s.subtotal_tiyin, s.commission_tiyin) for s in subs] == [
        (seller_a, 2_000, 200),
        (seller_b, 500, 50),
    ]
    [paid] = outbox(EventType.ORDER_PAID)
    assert [ref.id for ref in OrderPaid.model_validate(paid.payload).sub_orders] == [
        s.id for s in subs
    ]
    assert paid.correlation_id == order.id
    assert upstream.count("DELETE", f"/internal/cart/{order.customer_id}") == 1


def test_duplicate_payment_paid_changes_nothing(upstream: FakeUpstream) -> None:
    order = make_order()
    known_variants(upstream, order)
    event = payment_paid(order)
    saga.on_payment_paid(event)
    calls = len(upstream.calls)

    saga.on_payment_paid(event)

    assert len(outbox(EventType.ORDER_PAID)) == 1
    assert SubOrder.objects.count() == 1
    assert len(upstream.calls) == calls  # no rates read, no second cart clear


def test_payment_after_the_deadline_but_before_expiry_is_taken(upstream: FakeUpstream) -> None:
    order = make_order(reserved_until=timezone.now() - timedelta(minutes=1))
    known_variants(upstream, order)

    saga.on_payment_paid(payment_paid(order))

    assert reload(order).status == S.PAID.value
    assert outbox(EventType.ORDER_EXPIRED) == []


def test_payment_for_a_pending_order_is_retried_later(upstream: FakeUpstream) -> None:
    order = make_order(status=S.PENDING)
    known_variants(upstream, order)
    event = payment_paid(order)

    with pytest.raises(NotReserved):
        saga.on_payment_paid(event)

    assert not ProcessedEvent.objects.filter(event_id=event.event_id).exists()
    saga.on_stock_reserved(stock_reserved(order))
    saga.on_payment_paid(event)  # the redelivery succeeds
    assert reload(order).status == S.PAID.value


@pytest.mark.parametrize("status", [S.PAID, S.FULFILLING, S.COMPLETED, S.REFUNDED])
def test_payment_for_a_paid_or_refunded_order_does_nothing(
    upstream: FakeUpstream, status: OrderStatus
) -> None:
    order = make_order(status=status)

    saga.on_payment_paid(payment_paid(order))

    assert reload(order).status == status.value
    assert not Outbox.objects.exists()
    assert upstream.calls == []


def test_payment_for_a_cancelled_order_is_refunded() -> None:
    order = make_order(status=S.CANCELLED, lines=[(uuid4(), 7_000, 1)])

    saga.on_payment_paid(payment_paid(order, amount=7_000))

    assert reload(order).status == S.CANCELLED.value
    [refund] = outbox(EventType.ORDER_REFUND_REQUESTED)
    assert OrderRefundRequested.model_validate(refund.payload) == OrderRefundRequested(
        order_id=order.id, amount_tiyin=7_000, reason="ORDER_CANCELLED"
    )


def test_payment_amount_mismatch_is_logged_but_taken(
    upstream: FakeUpstream, caplog: pytest.LogCaptureFixture
) -> None:
    order = make_order()
    known_variants(upstream, order)

    with caplog.at_level(logging.WARNING, logger="orders.saga"):
        saga.on_payment_paid(payment_paid(order, amount=order.total_tiyin - 1))

    assert reload(order).status == S.PAID.value
    assert "payment amount differs from the order total" in caplog.text


def test_order_changed_after_the_unlocked_read_is_retried(
    upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = make_order()
    # What the unlocked read saw a moment before stock.reserved was handled.
    stale = Order(id=order.id, status=S.PENDING.value, total_tiyin=order.total_tiyin)
    monkeypatch.setattr(saga, "_get", lambda order_id: stale)
    event = payment_paid(order)

    with pytest.raises(StaleOrder):
        saga.on_payment_paid(event)

    assert reload(order).status == S.RESERVED.value
    assert not ProcessedEvent.objects.filter(event_id=event.event_id).exists()


# --- late payment -------------------------------------------------------------------------


def late_paid_order(upstream: FakeUpstream) -> Order:
    order = make_order(status=S.EXPIRED, lines=[(uuid4(), 4_000, 2), (uuid4(), 1_000, 1)])
    known_variants(upstream, order, rate="0.0500")
    saga.on_payment_paid(payment_paid(order))
    return reload(order)


def test_late_payment_asks_the_catalog_to_reserve_again(upstream: FakeUpstream) -> None:
    order = late_paid_order(upstream)

    assert order.status == S.EXPIRED.value
    assert order.late_payment is True
    [created] = outbox(EventType.ORDER_CREATED)
    payload = OrderCreated.model_validate(created.payload)
    assert payload.reserve_retry is True
    assert sorted((ref.variant_id, ref.qty) for ref in payload.items) == sorted(
        (item.variant_id, item.qty) for item in order.items.all()
    )
    assert not SubOrder.objects.exists()


def test_late_payment_then_stock_reserved_pays_the_order(upstream: FakeUpstream) -> None:
    order = late_paid_order(upstream)
    event = stock_reserved(order)

    saga.on_stock_reserved(event)
    saga.on_stock_reserved(event)  # duplicate

    order = reload(order)
    assert order.status == S.PAID.value
    assert order.reserved_until == StockReserved.model_validate(event.payload).expires_at
    assert statuses(order)[-1] == ("EXPIRED", "PAID", "LATE_PAYMENT")
    assert {s.commission_tiyin for s in SubOrder.objects.filter(order=order)} == {400, 50}
    assert len(outbox(EventType.ORDER_PAID)) == 1
    assert upstream.count("DELETE", f"/internal/cart/{order.customer_id}") == 1


def test_late_payment_then_stock_failed_refunds(upstream: FakeUpstream) -> None:
    order = late_paid_order(upstream)

    saga.on_stock_failed(stock_failed(order))

    order = reload(order)
    assert order.status == S.REFUNDED.value
    assert statuses(order)[-1] == ("EXPIRED", "REFUNDED", "LATE_PAYMENT_OUT_OF_STOCK")
    [refund] = outbox(EventType.ORDER_REFUND_REQUESTED)
    assert OrderRefundRequested.model_validate(refund.payload) == OrderRefundRequested(
        order_id=order.id, amount_tiyin=9_000, reason="LATE_PAYMENT_OUT_OF_STOCK"
    )
    assert outbox(EventType.ORDER_CANCELLED) == []
    assert not SubOrder.objects.exists()


def test_second_late_payment_does_not_reserve_twice(upstream: FakeUpstream) -> None:
    order = late_paid_order(upstream)

    saga.on_payment_paid(payment_paid(order))

    assert len(outbox(EventType.ORDER_CREATED)) == 1
    assert reload(order).status == S.EXPIRED.value


def test_late_reservation_needs_the_commission_rates(
    upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = late_paid_order(upstream)
    stale = reload(order)
    stale.late_payment = False  # the unlocked read saw no late payment yet
    monkeypatch.setattr(saga, "_get", lambda order_id: stale)

    with pytest.raises(StaleOrder):
        saga.on_stock_reserved(stock_reserved(order))

    assert reload(order).status == S.EXPIRED.value


def test_catalog_down_during_late_reservation_is_retried(upstream: FakeUpstream) -> None:
    order = late_paid_order(upstream)
    upstream.bulk_mode = "down"
    event = stock_reserved(order)

    with pytest.raises(ServiceUnavailable):
        saga.on_stock_reserved(event)

    assert reload(order).status == S.EXPIRED.value
    assert not ProcessedEvent.objects.filter(event_id=event.event_id).exists()


# --- payment.refunded ---------------------------------------------------------------------


@pytest.mark.parametrize("status", [S.PAID, S.FULFILLING, S.EXPIRED])
def test_full_refund_marks_the_order_refunded(status: OrderStatus) -> None:
    order = make_order(status=status)
    event = payment_refunded(order)

    saga.on_payment_refunded(event)
    saga.on_payment_refunded(event)  # duplicate

    order = reload(order)
    assert order.status == S.REFUNDED.value
    assert statuses(order)[-1] == (status.value, "REFUNDED", "PAYMENT_REFUNDED")
    assert OrderStatusHistory.objects.filter(order=order, to_status="REFUNDED").count() == 1


def test_partial_refund_of_one_cancelled_sub_order_keeps_the_order() -> None:
    seller_a, seller_b = uuid4(), uuid4()
    order, subs = make_paid_order(lines=[(seller_a, 1_000, 1), (seller_b, 2_000, 1)])
    SubOrder.objects.filter(id=subs[seller_a].id).update(
        status=SubOrderStatus.CANCELLED_BY_SELLER.value
    )

    saga.on_payment_refunded(payment_refunded(order, amount=1_000))

    assert reload(order).status == S.PAID.value


def test_refund_once_every_sub_order_is_cancelled_marks_the_order_refunded() -> None:
    seller_a, seller_b = uuid4(), uuid4()
    order, _ = make_paid_order(lines=[(seller_a, 1_000, 1), (seller_b, 2_000, 1)])
    SubOrder.objects.filter(order=order).update(status=SubOrderStatus.CANCELLED_BY_SELLER.value)

    saga.on_payment_refunded(payment_refunded(order, amount=2_000))

    assert reload(order).status == S.REFUNDED.value


@pytest.mark.parametrize("status", [S.PENDING, S.RESERVED, S.CANCELLED, S.COMPLETED, S.REFUNDED])
def test_refund_in_a_state_without_refunds_is_ignored(status: OrderStatus) -> None:
    order = make_order(status=status)
    history = statuses(order)

    saga.on_payment_refunded(payment_refunded(order))

    assert reload(order).status == status.value
    assert statuses(order) == history


def test_late_failure_refund_confirmation_is_ignored(upstream: FakeUpstream) -> None:
    order = late_paid_order(upstream)
    saga.on_stock_failed(stock_failed(order))

    saga.on_payment_refunded(payment_refunded(order))

    assert OrderStatusHistory.objects.filter(order=order, to_status="REFUNDED").count() == 1


# --- broken messages ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "make_event",
    [stock_reserved, stock_failed, payment_paid, payment_refunded],
)
def test_unknown_order_goes_to_the_dead_letter_queue(make_event: Any) -> None:
    ghost = Order(id=uuid4(), total_tiyin=1_000)
    event = make_event(ghost)

    with pytest.raises(PermanentError):
        HANDLERS[event.event_type](event)

    assert not ProcessedEvent.objects.exists()


def test_malformed_payload_is_a_validation_error() -> None:
    order = make_order(status=S.PENDING)
    event = stock_reserved(order)
    event.payload = {"order_id": str(order.id)}

    with pytest.raises(ValidationError):
        saga.on_stock_reserved(event)


# --- wiring and the whole saga ------------------------------------------------------------


def test_handlers_cover_exactly_the_bound_events() -> None:
    assert set(HANDLERS) == set(CONSUMER_BINDINGS["order"])


def deliver(handle: Any, event: EventEnvelope) -> None:
    """What the consumer does with a message body from order.q."""
    handle(event.model_dump_json().encode())


def test_full_saga_through_the_consumer(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    """checkout -> order.created -> stock.reserved -> payment.paid -> order.paid."""
    upstream.put_in_cart(customer_id, upstream.add_variant(price_tiyin=250_000), 2)
    handle = make_handler()

    order_id = checkout(api).json()["order_id"]
    status_url = f"/api/orders/{order_id}/status/"
    assert api.get(status_url).json()["status"] == "PENDING"

    [created] = outbox(EventType.ORDER_CREATED)
    order = Order.objects.get(id=OrderCreated.model_validate(created.payload).order_id)
    deliver(handle, stock_reserved(order))
    body = api.get(status_url).json()
    assert body["status"] == "RESERVED"
    assert body["reserved_until"] is not None

    deliver(handle, payment_paid(reload(order)))
    assert api.get(status_url).json()["status"] == "PAID"

    assert [h[1] for h in statuses(order)] == ["PENDING", "RESERVED", "PAID"]
    [paid] = outbox(EventType.ORDER_PAID)
    assert OrderPaid.model_validate(paid.payload).sub_orders[0].subtotal_tiyin == 500_000
    assert customer_id not in upstream.carts
    assert ProcessedEvent.objects.count() == 2


def test_consumer_ignores_events_it_has_no_handler_for() -> None:
    order = make_order()
    event = incoming(OrderExpired(order_id=order.id, items=services.item_refs(order.id)))

    deliver(make_handler(), event)

    assert not ProcessedEvent.objects.exists()
