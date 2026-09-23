"""Every product change leaves exactly one outbox row, in the same transaction."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.db import transaction

from contracts.enums import EventType, ProductStatus
from contracts.events import (
    EventEnvelope,
    ProductDeleted,
    ProductUpdated,
    SellerApproved,
    build_event,
)
from messaging.models import Outbox
from messaging.outbox import (
    DjangoOutboxStore,
    OutsideTransactionError,
    add_to_outbox,
    mark_processed,
    to_envelope,
)
from products import services
from products.documents import build_product_document
from products.models import AttributeValue, Category, ImageStatus
from py_common.outbox import publish_pending
from sellers.models import Seller
from tests.factories import make_image, make_product, make_variant

pytestmark = pytest.mark.django_db


def only_event() -> EventEnvelope:
    row = Outbox.objects.get()
    return to_envelope(row)


def test_create_active_product_writes_product_updated(
    seller: Seller, categories: dict[str, Category]
) -> None:
    product = services.create_product(
        seller,
        title="Galaxy S25",
        category=categories["smartphones"],
        description="Flagship",
        status=ProductStatus.ACTIVE.value,
    )

    event = only_event()
    assert event.event_type is EventType.PRODUCT_UPDATED
    assert event.producer == "catalog"
    assert event.correlation_id == product.id
    document = ProductUpdated.model_validate(event.payload)
    assert document.product_id == product.id
    assert document.seller_id == seller.id
    assert document.shop_name == "Tashkent Tech"
    assert document.title == "Galaxy S25"
    assert document.slug == "galaxy-s25"
    assert document.description == "Flagship"
    assert document.category_path == ["Electronics", "Phones", "Smartphones"]
    assert document.category_ids == [
        categories["electronics"].id,
        categories["phones"].id,
        categories["smartphones"].id,
    ]
    assert (document.min_price_tiyin, document.max_price_tiyin) == (0, 0)
    assert document.in_stock is False
    assert document.rating == 0
    assert document.image_url is None


def test_draft_product_is_not_indexable(seller: Seller, categories: dict[str, Category]) -> None:
    product = services.create_product(seller, title="Draft", category=categories["laptops"])

    event = only_event()
    assert event.event_type is EventType.PRODUCT_DELETED
    assert ProductDeleted.model_validate(event.payload).product_id == product.id


def test_update_writes_a_fresh_document(seller: Seller, categories: dict[str, Category]) -> None:
    product = make_product(seller=seller, category=categories["phones"])

    services.update_product(seller, product.id, title="Renamed", category=categories["laptops"])

    document = ProductUpdated.model_validate(only_event().payload)
    assert document.title == "Renamed"
    assert document.category_path == ["Electronics", "Laptops"]


def test_becoming_draft_emits_product_deleted(
    seller: Seller, categories: dict[str, Category]
) -> None:
    product = make_product(seller=seller, category=categories["phones"])

    services.update_product(seller, product.id, status=ProductStatus.DRAFT.value)

    assert only_event().event_type is EventType.PRODUCT_DELETED


def test_archive_emits_product_deleted_once(seller: Seller) -> None:
    product = make_product(seller=seller)

    services.archive_product(seller, product.id)
    services.archive_product(seller, product.id)  # already archived: nothing new

    event = only_event()
    assert event.event_type is EventType.PRODUCT_DELETED
    assert ProductDeleted.model_validate(event.payload) == ProductDeleted(product_id=product.id)


def test_variant_changes_write_documents_with_prices_and_stock(
    seller: Seller, attributes: dict[str, AttributeValue]
) -> None:
    product = make_product(seller=seller)

    services.create_variant(
        seller,
        product.id,
        sku="S25-RED-128",
        price_tiyin=1_200_000_000,
        stock=0,
        attribute_value_ids=[attributes["red"].id, attributes["128"].id],
    )
    variant = services.create_variant(
        seller,
        product.id,
        sku="S25-BLK-256",
        price_tiyin=1_500_000_000,
        stock=3,
        attribute_value_ids=[attributes["black"].id, attributes["256"].id],
    )
    services.set_variant_stock(seller, variant.id, 5)

    rows = list(Outbox.objects.order_by("id"))
    assert len(rows) == 3
    last = ProductUpdated.model_validate(rows[-1].payload)
    assert last.min_price_tiyin == 1_200_000_000
    assert last.max_price_tiyin == 1_500_000_000
    assert last.in_stock is True
    assert [(a.code, a.value) for a in last.attributes] == [
        ("color", "black"),
        ("color", "red"),
        ("memory", "128 GB"),
        ("memory", "256 GB"),
    ]


def test_inactive_variants_do_not_count(seller: Seller) -> None:
    product = make_product(seller=seller)
    make_variant(product=product, price_tiyin=100, stock=5)
    hidden = make_variant(product=product, price_tiyin=50, stock=5)

    services.update_variant(seller, hidden.id, is_active=False)

    document = ProductUpdated.model_validate(only_event().payload)
    assert (document.min_price_tiyin, document.max_price_tiyin) == (100, 100)


def test_fully_reserved_stock_is_not_in_stock(seller: Seller) -> None:
    product = make_product(seller=seller)
    make_variant(product=product, stock=2, reserved=2)

    document = build_product_document(product)

    assert document.in_stock is False


def test_document_uses_first_ready_image(seller: Seller) -> None:
    product = make_product(seller=seller)
    make_image(product=product, position=0, status=ImageStatus.PROCESSING)
    ready = make_image(product=product, position=1)
    make_image(product=product, position=2)

    document = build_product_document(product)

    assert document.image_url == f"http://minio.localhost/catalog-test/{ready.medium_key}"


def test_rolled_back_change_leaves_no_outbox_row(
    seller: Seller, categories: dict[str, Category]
) -> None:
    class Boom(Exception):
        pass

    with pytest.raises(Boom), transaction.atomic():
        services.create_product(
            seller,
            title="Never",
            category=categories["phones"],
            status=ProductStatus.ACTIVE.value,
        )
        raise Boom

    assert Outbox.objects.count() == 0


def test_failed_business_rule_leaves_no_outbox_row(seller: Seller) -> None:
    variant = make_variant(product=make_product(seller=seller), stock=5, reserved=4)

    with pytest.raises(Exception, match="reserved"):
        services.set_variant_stock(seller, variant.id, 3)

    assert Outbox.objects.count() == 0


def _event() -> EventEnvelope:
    return build_event(
        SellerApproved(user_id=uuid4(), shop_name="x"),
        producer="catalog",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.django_db(transaction=True)
def test_outbox_requires_a_transaction() -> None:
    with pytest.raises(OutsideTransactionError):
        add_to_outbox(_event())
    with pytest.raises(OutsideTransactionError):
        mark_processed(_event())


def test_store_publishes_pending_rows_once() -> None:
    with transaction.atomic():
        first = add_to_outbox(_event())
        second = add_to_outbox(_event())

    class Recorder:
        def __init__(self) -> None:
            self.sent: list[EventEnvelope] = []

        def publish(self, envelope: EventEnvelope) -> None:
            self.sent.append(envelope)

    publisher = Recorder()
    store = DjangoOutboxStore()
    with transaction.atomic():
        assert publish_pending(store, publisher) == 2
    with transaction.atomic():
        assert publish_pending(store, publisher) == 0

    assert [e.event_id for e in publisher.sent] == [first.event_id, second.event_id]
    assert publisher.sent[0].producer == "catalog"
    assert not Outbox.objects.filter(published_at__isnull=True).exists()
