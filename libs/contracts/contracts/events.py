"""Event envelope and payload schemas for every event on the marketplace exchange."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import EventType, PaymentProvider, SubOrderStatus
from contracts.ids import uuid7
from contracts.money import Tiyin


class Frozen(BaseModel):
    """Base for payloads: immutable and strict about unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EventEnvelope(BaseModel):
    """Transport envelope. ``event_id`` is the idempotency key for consumers."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid7)
    event_type: EventType
    occurred_at: datetime
    producer: str
    correlation_id: UUID
    version: int = 1
    payload: dict[str, Any]


class OrderItemRef(Frozen):
    variant_id: UUID
    qty: int = Field(gt=0)


class OrderCreated(Frozen):
    order_id: UUID
    items: list[OrderItemRef] = Field(min_length=1)
    reserve_retry: bool = False


class StockReserved(Frozen):
    order_id: UUID
    expires_at: datetime


class StockFailed(Frozen):
    order_id: UUID
    reason: str
    variant_ids: list[UUID] = Field(default_factory=list)


class PaymentPaid(Frozen):
    order_id: UUID
    transaction_id: UUID
    amount_tiyin: Tiyin
    provider: PaymentProvider


class PaymentRefunded(Frozen):
    order_id: UUID
    amount_tiyin: Tiyin


class SubOrderRef(Frozen):
    id: UUID
    seller_id: UUID
    items: list[OrderItemRef] = Field(min_length=1)
    subtotal_tiyin: Tiyin
    commission_tiyin: Tiyin


class OrderPaid(Frozen):
    order_id: UUID
    customer_id: UUID
    sub_orders: list[SubOrderRef] = Field(min_length=1)


class OrderExpired(Frozen):
    order_id: UUID
    items: list[OrderItemRef] = Field(min_length=1)


class OrderCancelled(Frozen):
    order_id: UUID
    items: list[OrderItemRef] = Field(min_length=1)
    reason: str


class OrderRefundRequested(Frozen):
    order_id: UUID
    amount_tiyin: Tiyin
    reason: str


class SubOrderStatusChanged(Frozen):
    sub_order_id: UUID
    order_id: UUID
    seller_id: UUID
    customer_id: UUID
    status: SubOrderStatus


class ProductAttribute(Frozen):
    code: str
    value: str


class ProductUpdated(Frozen):
    """Full search document: the search service indexes this payload as is."""

    product_id: UUID
    seller_id: UUID
    shop_name: str
    title: str
    slug: str
    description: str = ""
    category_ids: list[UUID] = Field(default_factory=list)
    category_path: list[str] = Field(default_factory=list)
    min_price_tiyin: Tiyin
    max_price_tiyin: Tiyin
    in_stock: bool
    attributes: list[ProductAttribute] = Field(default_factory=list)
    rating: float = 0.0
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ProductDeleted(Frozen):
    product_id: UUID


class SellerApproved(Frozen):
    user_id: UUID
    shop_name: str


#: Every event type and the model describing its payload.
PAYLOAD_MODELS: dict[EventType, type[Frozen]] = {
    EventType.ORDER_CREATED: OrderCreated,
    EventType.STOCK_RESERVED: StockReserved,
    EventType.STOCK_FAILED: StockFailed,
    EventType.PAYMENT_PAID: PaymentPaid,
    EventType.PAYMENT_REFUNDED: PaymentRefunded,
    EventType.ORDER_PAID: OrderPaid,
    EventType.ORDER_EXPIRED: OrderExpired,
    EventType.ORDER_CANCELLED: OrderCancelled,
    EventType.ORDER_REFUND_REQUESTED: OrderRefundRequested,
    EventType.SUB_ORDER_STATUS_CHANGED: SubOrderStatusChanged,
    EventType.PRODUCT_UPDATED: ProductUpdated,
    EventType.PRODUCT_DELETED: ProductDeleted,
    EventType.SELLER_APPROVED: SellerApproved,
}

_EVENT_TYPE_BY_MODEL: dict[type[Frozen], EventType] = {
    model: event_type for event_type, model in PAYLOAD_MODELS.items()
}


def payload_model_for(event_type: EventType) -> type[Frozen]:
    """Return the payload model of an event type."""
    return PAYLOAD_MODELS[event_type]


def build_event(
    payload: Frozen,
    *,
    producer: str,
    correlation_id: UUID,
    occurred_at: datetime,
    event_id: UUID | None = None,
    version: int = 1,
) -> EventEnvelope:
    """Wrap a payload model into an envelope, deriving the event type from the model."""
    event_type = _EVENT_TYPE_BY_MODEL[type(payload)]
    return EventEnvelope(
        event_id=event_id or uuid7(),
        event_type=event_type,
        occurred_at=occurred_at,
        producer=producer,
        correlation_id=correlation_id,
        version=version,
        payload=payload.model_dump(mode="json"),
    )


def parse_payload(envelope: EventEnvelope) -> Frozen:
    """Validate and return the typed payload of an envelope."""
    return payload_model_for(envelope.event_type).model_validate(envelope.payload)
