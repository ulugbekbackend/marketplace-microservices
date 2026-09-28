"""The order and sub-order state machines."""

from uuid import uuid4

import pytest
from django.db import transaction

from contracts.enums import OrderStatus, SubOrderStatus
from orders.models import OrderStatusHistory, SubOrder, SubOrderStatusHistory
from orders.state import (
    ORDER_TRANSITIONS,
    SUB_ORDER_TRANSITIONS,
    InvalidTransition,
    NotInTransaction,
    can_transition,
    lock_order,
    lock_sub_order,
    transition,
    transition_sub_order,
)
from tests.factories import make_order

pytestmark = pytest.mark.django_db

S = OrderStatus
ALLOWED = [
    (S.PENDING, S.RESERVED),
    (S.PENDING, S.CANCELLED),
    (S.RESERVED, S.PAID),
    (S.RESERVED, S.EXPIRED),
    (S.RESERVED, S.CANCELLED),
    (S.PAID, S.FULFILLING),
    (S.PAID, S.REFUNDED),
    (S.FULFILLING, S.COMPLETED),
    (S.FULFILLING, S.REFUNDED),
    (S.EXPIRED, S.PAID),
    (S.EXPIRED, S.REFUNDED),
]


def test_the_table_is_exactly_the_specified_one() -> None:
    table = {(src, dst) for src, targets in ORDER_TRANSITIONS.items() for dst in targets}
    assert table == set(ALLOWED)
    assert set(ORDER_TRANSITIONS) == set(OrderStatus)


@pytest.mark.parametrize(("source", "target"), ALLOWED)
def test_allowed_transition_changes_status_and_writes_history(
    source: OrderStatus, target: OrderStatus
) -> None:
    order = make_order(status=source)

    with transaction.atomic():
        transition(lock_order(order.id), target, reason="because")

    order.refresh_from_db()
    assert order.status == target.value
    last = OrderStatusHistory.objects.filter(order=order).last()
    assert last is not None
    assert (last.from_status, last.to_status, last.reason) == (
        source.value,
        target.value,
        "because",
    )


DISALLOWED = [
    (S.PENDING, S.PAID),
    (S.PENDING, S.EXPIRED),
    (S.RESERVED, S.COMPLETED),
    (S.RESERVED, S.RESERVED),
    (S.PAID, S.CANCELLED),
    (S.PAID, S.EXPIRED),
    (S.FULFILLING, S.CANCELLED),
    (S.EXPIRED, S.RESERVED),
    (S.CANCELLED, S.RESERVED),
    (S.CANCELLED, S.PAID),
    (S.COMPLETED, S.REFUNDED),
    (S.REFUNDED, S.PAID),
]


@pytest.mark.parametrize(("source", "target"), DISALLOWED)
def test_disallowed_transition_raises_and_changes_nothing(
    source: OrderStatus, target: OrderStatus
) -> None:
    order = make_order(status=source)
    history_before = OrderStatusHistory.objects.count()

    with pytest.raises(InvalidTransition) as caught, transaction.atomic():
        transition(lock_order(order.id), target)

    assert caught.value.status_code == 409
    assert caught.value.error_code == "INVALID_TRANSITION"
    assert caught.value.details == {"from": source.value, "to": target.value}
    order.refresh_from_db()
    assert order.status == source.value
    assert OrderStatusHistory.objects.count() == history_before
    assert not can_transition(source, target)


def test_cancel_stores_the_reason_on_the_order() -> None:
    order = make_order(status=S.RESERVED)

    with transaction.atomic():
        transition(lock_order(order.id), S.CANCELLED, reason="OUT_OF_STOCK")

    order.refresh_from_db()
    assert order.cancel_reason == "OUT_OF_STOCK"


@pytest.mark.django_db(transaction=True)
def test_status_changes_need_a_transaction() -> None:
    order = make_order(status=S.RESERVED)

    with pytest.raises(NotInTransaction):
        transition(order, S.PAID)
    with pytest.raises(NotInTransaction):
        lock_order(order.id)


SUB_ALLOWED = [
    (SubOrderStatus.NEW, SubOrderStatus.ACCEPTED),
    (SubOrderStatus.NEW, SubOrderStatus.CANCELLED_BY_SELLER),
    (SubOrderStatus.ACCEPTED, SubOrderStatus.SHIPPED),
    (SubOrderStatus.ACCEPTED, SubOrderStatus.CANCELLED_BY_SELLER),
    (SubOrderStatus.SHIPPED, SubOrderStatus.DELIVERED),
]


def test_sub_order_table_is_exactly_the_specified_one() -> None:
    table = {(src, dst) for src, targets in SUB_ORDER_TRANSITIONS.items() for dst in targets}
    assert table == set(SUB_ALLOWED)


@pytest.mark.parametrize(("source", "target"), SUB_ALLOWED)
def test_sub_order_allowed_transitions(source: SubOrderStatus, target: SubOrderStatus) -> None:
    sub_order = SubOrder.objects.create(
        order=make_order(status=S.PAID), seller_id=uuid4(), subtotal_tiyin=100, status=source
    )

    with transaction.atomic():
        transition_sub_order(sub_order, target, reason="why", tracking_number="UZ-1")

    sub_order.refresh_from_db()
    assert sub_order.status == target.value
    [row] = SubOrderStatusHistory.objects.filter(sub_order=sub_order)
    assert (row.from_status, row.to_status, row.reason) == (source.value, target.value, "why")
    shipped = target is SubOrderStatus.SHIPPED
    cancelled = target is SubOrderStatus.CANCELLED_BY_SELLER
    assert sub_order.tracking_number == ("UZ-1" if shipped else "")
    assert sub_order.cancel_reason == ("why" if cancelled else "")


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (SubOrderStatus.NEW, SubOrderStatus.SHIPPED),
        (SubOrderStatus.SHIPPED, SubOrderStatus.CANCELLED_BY_SELLER),
        (SubOrderStatus.DELIVERED, SubOrderStatus.NEW),
        (SubOrderStatus.CANCELLED_BY_SELLER, SubOrderStatus.ACCEPTED),
    ],
)
def test_sub_order_disallowed_transitions(source: SubOrderStatus, target: SubOrderStatus) -> None:
    sub_order = SubOrder.objects.create(
        order=make_order(status=S.PAID), seller_id=uuid4(), subtotal_tiyin=100, status=source
    )

    with pytest.raises(InvalidTransition), transaction.atomic():
        transition_sub_order(sub_order, target)
    assert not SubOrderStatusHistory.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_sub_order_changes_need_a_transaction() -> None:
    sub_order = SubOrder.objects.create(
        order=make_order(status=S.PAID), seller_id=uuid4(), subtotal_tiyin=100
    )

    with pytest.raises(NotInTransaction):
        transition_sub_order(sub_order, SubOrderStatus.ACCEPTED)
    with pytest.raises(NotInTransaction):
        lock_sub_order(sub_order.id)
