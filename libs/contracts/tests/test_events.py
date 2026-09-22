"""Every event type has a valid sample payload and survives an envelope round trip."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.enums import EventType, PaymentProvider, SubOrderStatus
from contracts.events import (
    PAYLOAD_MODELS,
    EventEnvelope,
    Frozen,
    OrderCancelled,
    OrderCreated,
    OrderExpired,
    OrderItemRef,
    OrderPaid,
    OrderRefundRequested,
    PaymentPaid,
    PaymentRefunded,
    ProductAttribute,
    ProductDeleted,
    ProductUpdated,
    SellerApproved,
    StockFailed,
    StockReserved,
    SubOrderRef,
    SubOrderStatusChanged,
    build_event,
    parse_payload,
    payload_model_for,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
ORDER_ID = uuid4()
ITEM = OrderItemRef(variant_id=uuid4(), qty=2)

SAMPLES: dict[EventType, Frozen] = {
    EventType.ORDER_CREATED: OrderCreated(order_id=ORDER_ID, items=[ITEM]),
    EventType.STOCK_RESERVED: StockReserved(order_id=ORDER_ID, expires_at=NOW),
    EventType.STOCK_FAILED: StockFailed(
        order_id=ORDER_ID, reason="OUT_OF_STOCK", variant_ids=[ITEM.variant_id]
    ),
    EventType.PAYMENT_PAID: PaymentPaid(
        order_id=ORDER_ID,
        transaction_id=uuid4(),
        amount_tiyin=125_000_00,
        provider=PaymentProvider.PAYME,
    ),
    EventType.PAYMENT_REFUNDED: PaymentRefunded(order_id=ORDER_ID, amount_tiyin=125_000_00),
    EventType.ORDER_PAID: OrderPaid(
        order_id=ORDER_ID,
        customer_id=uuid4(),
        sub_orders=[
            SubOrderRef(
                id=uuid4(),
                seller_id=uuid4(),
                items=[ITEM],
                subtotal_tiyin=125_000_00,
                commission_tiyin=12_500_00,
            )
        ],
    ),
    EventType.ORDER_EXPIRED: OrderExpired(order_id=ORDER_ID, items=[ITEM]),
    EventType.ORDER_CANCELLED: OrderCancelled(order_id=ORDER_ID, items=[ITEM], reason="BY_USER"),
    EventType.ORDER_REFUND_REQUESTED: OrderRefundRequested(
        order_id=ORDER_ID, amount_tiyin=125_000_00, reason="LATE_PAYMENT_NO_STOCK"
    ),
    EventType.SUB_ORDER_STATUS_CHANGED: SubOrderStatusChanged(
        sub_order_id=uuid4(),
        order_id=ORDER_ID,
        seller_id=uuid4(),
        customer_id=uuid4(),
        status=SubOrderStatus.SHIPPED,
    ),
    EventType.PRODUCT_UPDATED: ProductUpdated(
        product_id=uuid4(),
        seller_id=uuid4(),
        shop_name="Oqtepa Savdo",
        title="Samsung Galaxy A55",
        slug="samsung-galaxy-a55",
        category_ids=[uuid4()],
        category_path=["Elektronika", "Telefonlar", "Smartfonlar"],
        min_price_tiyin=3_500_000_00,
        max_price_tiyin=4_200_000_00,
        in_stock=True,
        attributes=[ProductAttribute(code="color", value="qora")],
        created_at=NOW,
        updated_at=NOW,
    ),
    EventType.PRODUCT_DELETED: ProductDeleted(product_id=uuid4()),
    EventType.SELLER_APPROVED: SellerApproved(user_id=uuid4(), shop_name="Oqtepa Savdo"),
}


def test_every_event_type_has_a_payload_model() -> None:
    assert set(PAYLOAD_MODELS) == set(EventType)


def test_every_event_type_has_a_sample() -> None:
    assert set(SAMPLES) == set(EventType)


@pytest.mark.parametrize("event_type", list(EventType))
def test_round_trip_through_envelope(event_type: EventType) -> None:
    payload = SAMPLES[event_type]
    envelope = build_event(payload, producer="tests", correlation_id=ORDER_ID, occurred_at=NOW)

    assert envelope.event_type is event_type
    assert envelope.version == 1

    wire = envelope.model_dump_json()
    restored = EventEnvelope.model_validate_json(wire)
    assert parse_payload(restored) == payload
    assert isinstance(parse_payload(restored), payload_model_for(event_type))


def test_envelope_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_type="order.teleported",
            occurred_at=NOW,
            producer="tests",
            correlation_id=ORDER_ID,
            payload={},
        )


def test_payload_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        OrderCreated.model_validate(
            {"order_id": str(ORDER_ID), "items": [ITEM.model_dump(mode="json")], "total": 10}
        )


def test_payloads_are_immutable() -> None:
    payload = ProductDeleted(product_id=uuid4())
    with pytest.raises(ValidationError):
        payload.product_id = uuid4()  # type: ignore[misc]


def test_negative_amount_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PaymentRefunded(order_id=ORDER_ID, amount_tiyin=-1)


def test_order_created_requires_items() -> None:
    with pytest.raises(ValidationError):
        OrderCreated(order_id=ORDER_ID, items=[])


def test_item_qty_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        OrderItemRef(variant_id=uuid4(), qty=0)


def test_reserve_retry_defaults_to_false() -> None:
    assert SAMPLES[EventType.ORDER_CREATED].model_dump()["reserve_retry"] is False
