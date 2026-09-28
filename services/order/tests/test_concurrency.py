"""Concurrency against real Postgres: row locks make payment and expiry safe to race."""

import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone

from contracts.enums import EventType, OrderStatus, SubOrderStatus, UserRole
from messaging.models import Outbox
from orders import services
from orders.models import Order, SubOrder, SubOrderStatusHistory
from tests.conftest import FakeUpstream, user_client
from tests.factories import make_order, make_paid_order, make_sub_order

pytestmark = pytest.mark.django_db(transaction=True)


def run_in_threads(target: Callable[[], Any], count: int) -> list[BaseException]:
    errors: list[BaseException] = []
    barrier = threading.Barrier(count)

    def worker() -> None:
        try:
            barrier.wait()
            target()
        except BaseException as exc:  # collected and asserted by the test
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def known_variants(upstream: FakeUpstream, order: Order) -> None:
    for item in order.items.all():
        template = upstream.variants[upstream.add_variant(seller_id=item.seller_id)]
        upstream.variants[item.variant_id] = {**template, "variant_id": str(item.variant_id)}


def test_concurrent_payments_split_the_order_once(upstream: FakeUpstream) -> None:
    order = make_order(lines=[(uuid4(), 1_000, 1), (uuid4(), 2_000, 2)])
    known_variants(upstream, order)

    errors = run_in_threads(lambda: services.mark_paid(order.id), 4)

    assert errors == []
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID.value
    assert SubOrder.objects.filter(order=order).count() == 2
    assert Outbox.objects.filter(event_type=EventType.ORDER_PAID.value).count() == 1


def test_expiry_skips_orders_locked_by_someone_else(upstream: FakeUpstream) -> None:
    past = timezone.now() - timedelta(minutes=1)
    locked = make_order(reserved_until=past)
    free = make_order(reserved_until=past)
    holding = threading.Event()
    done = threading.Event()

    def hold_lock() -> None:
        with transaction.atomic():
            Order.objects.select_for_update().get(id=locked.id)
            holding.set()
            done.wait(timeout=10)
        connections.close_all()

    holder = threading.Thread(target=hold_lock)
    holder.start()
    holding.wait(timeout=10)
    try:
        assert services.expire_overdue() == 1
    finally:
        done.set()
        holder.join()

    assert Order.objects.get(id=free.id).status == OrderStatus.EXPIRED.value
    assert Order.objects.get(id=locked.id).status == OrderStatus.RESERVED.value
    assert connection.vendor == "postgresql"


def test_parallel_seller_changes_on_one_sub_order_let_exactly_one_win() -> None:
    seller_id = uuid4()
    sub_order = make_sub_order(seller_id, status=SubOrderStatus.ACCEPTED)
    url = f"/api/orders/seller/{sub_order.id}/status/"
    bodies = iter(
        [
            {"status": "SHIPPED", "tracking_number": "UZ-1"},
            {"status": "CANCELLED_BY_SELLER", "reason": "Damaged"},
        ]
    )
    lock = threading.Lock()
    codes: list[int] = []

    def change() -> None:
        with lock:
            body = next(bodies)
        response = user_client(seller_id, UserRole.SELLER).patch(url, body, format="json")
        with lock:
            codes.append(response.status_code)

    errors = run_in_threads(change, 2)

    assert errors == []
    assert sorted(codes) == [200, 409]
    sub_order.refresh_from_db()
    assert sub_order.status in {
        SubOrderStatus.SHIPPED.value,
        SubOrderStatus.CANCELLED_BY_SELLER.value,
    }
    assert SubOrderStatusHistory.objects.filter(sub_order=sub_order).count() == 2  # created + 1
    assert Outbox.objects.filter(event_type=EventType.SUB_ORDER_STATUS_CHANGED.value).count() == 1
    refunds = Outbox.objects.filter(event_type=EventType.ORDER_REFUND_REQUESTED.value).count()
    assert refunds == (sub_order.status == SubOrderStatus.CANCELLED_BY_SELLER.value)


def test_parallel_deliveries_of_the_last_sub_orders_complete_the_order_once() -> None:
    sellers = [uuid4(), uuid4()]
    order, subs = make_paid_order(
        lines=[(seller, 1_000, 1) for seller in sellers], status=OrderStatus.FULFILLING
    )
    SubOrder.objects.filter(order=order).update(status=SubOrderStatus.SHIPPED.value)
    targets = iter(subs.values())
    lock = threading.Lock()

    def deliver() -> None:
        with lock:
            sub_order = next(targets)
        response = user_client(sub_order.seller_id, UserRole.SELLER).patch(
            f"/api/orders/seller/{sub_order.id}/status/", {"status": "DELIVERED"}, format="json"
        )
        assert response.status_code == 200

    errors = run_in_threads(deliver, 2)

    assert errors == []
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED.value
    assert order.history.filter(to_status=OrderStatus.COMPLETED.value).count() == 1
