"""Concurrency against real Postgres: row locks make payment and expiry safe to race."""

import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone

from contracts.enums import EventType, OrderStatus
from messaging.models import Outbox
from orders import services
from orders.models import Order, SubOrder
from tests.conftest import FakeUpstream
from tests.factories import make_order

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
