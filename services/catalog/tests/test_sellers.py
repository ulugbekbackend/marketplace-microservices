"""seller.approved creates the shop once, whatever the number of deliveries."""

import threading
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.db import connection

from contracts.events import EventEnvelope, OrderCreated, OrderItemRef, SellerApproved, build_event
from messaging.models import ProcessedEvent
from sellers.models import Seller
from sellers.services import handle_seller_approved


def approved_event(user_id: UUID | None = None, shop_name: str = "Chorsu Bozori") -> EventEnvelope:
    return build_event(
        SellerApproved(user_id=user_id or uuid4(), shop_name=shop_name),
        producer="auth",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.django_db
def test_creates_seller_with_user_id_as_primary_key() -> None:
    user_id = uuid4()
    event = approved_event(user_id, "Chorsu Bozori")

    assert handle_seller_approved(event) is True

    seller = Seller.objects.get()
    assert seller.id == user_id
    assert seller.user_id == user_id
    assert seller.shop_name == "Chorsu Bozori"
    assert seller.slug == "chorsu-bozori"
    assert seller.is_verified is True
    assert seller.commission_rate == Decimal("0.1000")
    assert ProcessedEvent.objects.filter(event_id=event.event_id).exists()


@pytest.mark.django_db
def test_same_event_twice_creates_one_seller() -> None:
    event = approved_event()

    assert handle_seller_approved(event) is True
    assert handle_seller_approved(event) is False

    assert Seller.objects.count() == 1
    assert ProcessedEvent.objects.count() == 1


@pytest.mark.django_db
def test_new_approval_of_existing_seller_updates_the_shop() -> None:
    user_id = uuid4()
    handle_seller_approved(approved_event(user_id, "Old name"))

    assert handle_seller_approved(approved_event(user_id, "New name")) is True

    seller = Seller.objects.get()
    assert seller.shop_name == "New name"
    assert seller.slug == "old-name"  # shop URLs stay stable


@pytest.mark.django_db
def test_cyrillic_shop_names_get_unique_ascii_slugs() -> None:
    handle_seller_approved(approved_event(shop_name="Ширин дўкон"))
    handle_seller_approved(approved_event(shop_name="Ширин дўкон"))

    assert sorted(Seller.objects.values_list("slug", flat=True)) == [
        "shirin-dukon",
        "shirin-dukon-2",
    ]


def test_rejects_other_event_types() -> None:
    event = build_event(
        OrderCreated(order_id=uuid4(), items=[OrderItemRef(variant_id=uuid4(), qty=1)]),
        producer="order",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )

    with pytest.raises(ValueError, match=r"seller\.approved"):
        handle_seller_approved(event)


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_deliveries_create_one_seller() -> None:
    event = approved_event()
    workers = 4
    barrier = threading.Barrier(workers)
    results: list[bool] = []
    errors: list[BaseException] = []

    def deliver() -> None:
        try:
            barrier.wait()
            results.append(handle_seller_approved(event))
        except BaseException as exc:  # surfaced by the assertion below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=deliver) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(results) == [False] * (workers - 1) + [True]
    assert Seller.objects.count() == 1
    assert ProcessedEvent.objects.count() == 1
