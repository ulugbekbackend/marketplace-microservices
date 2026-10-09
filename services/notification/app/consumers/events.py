"""``notification.q`` consumer: which event tells whom, with which template.

    order.paid                customer + every seller of the order
    order.expired / cancelled customer (looked up through the order service)
    payment.refunded          customer (looked up through the order service)
    sub_order.status_changed  customer, from ACCEPTED on (NEW is covered by order.paid)
    seller.approved           the new seller

Every event is handled once (``RedisIdempotencyStore``); a failure releases it for the
broker's retry, and after the last retry it lands in the DLQ.
"""

import logging
from uuid import UUID

from app.services.directory import Directory
from app.services.notifier import Notifier
from contracts.enums import EventType, SubOrderStatus
from contracts.events import (
    EventEnvelope,
    OrderCancelled,
    OrderExpired,
    OrderPaid,
    PaymentRefunded,
    SellerApproved,
    SubOrderStatusChanged,
)
from contracts.money import format_tiyin
from py_common.consumer import EventRouter, Outcome
from py_common.idempotency import IdempotencyStore

logger = logging.getLogger(__name__)

SERVICE = "notification"

CANCEL_REASONS = {
    "OUT_OF_STOCK": "Mahsulot omborda qolmagan edi.",
    "RESERVATION_FAILED": "Mahsulotlarni band qilib bo'lmadi.",
    "CANCELLED_BY_CUSTOMER": "Siz bekor qildingiz.",
    "RESERVATION_EXPIRED": "To'lov belgilangan vaqtda qilinmadi.",
}

SUB_ORDER_TEXTS = {
    SubOrderStatus.ACCEPTED: ("qabul qilindi", "Do'kon buyurtmangizni qabul qildi va yig'moqda."),
    SubOrderStatus.SHIPPED: ("yo'lda", "Buyurtmangiz jo'natildi, tez orada yetib boradi."),
    SubOrderStatus.DELIVERED: ("yetkazildi", "Buyurtmangiz yetkazildi. Xaridingiz uchun rahmat!"),
    SubOrderStatus.CANCELLED_BY_SELLER: (
        "do'kon bekor qildi",
        "Do'kon buyurtmaning bir qismini bekor qildi. Shu qism uchun pul qaytariladi.",
    ),
}


def order_number(order_id: UUID) -> str:
    return f"#{str(order_id)[:8].upper()}"


class Links:
    def __init__(self, shop_url: str, seller_url: str) -> None:
        self._shop = shop_url.rstrip("/")
        self._seller = seller_url.rstrip("/")

    def order(self, order_id: UUID) -> str:
        return f"{self._shop}/orders/{order_id}"

    def seller_order(self, sub_order_id: UUID) -> str:
        return f"{self._seller}/orders/{sub_order_id}"

    def seller_home(self) -> str:
        return f"{self._seller}/"


def build_router(
    store: IdempotencyStore, notifier: Notifier, directory: Directory, links: Links
) -> EventRouter:
    router = EventRouter(SERVICE, store)

    async def to_customer_of(
        envelope: EventEnvelope, order_id: UUID, template: str, context: dict[str, object]
    ) -> None:
        customer_id = await directory.customer_of(order_id)
        if customer_id is None:
            logger.warning("order without a customer", extra={"order_id": str(order_id)})
            return
        await notifier.notify(envelope.event_id, customer_id, template, context)

    @router.on(EventType.ORDER_PAID)
    async def on_order_paid(envelope: EventEnvelope) -> None:
        event = OrderPaid.model_validate(envelope.payload)
        number = order_number(event.order_id)
        total = sum(sub.subtotal_tiyin for sub in event.sub_orders)
        await notifier.notify(
            envelope.event_id,
            event.customer_id,
            "order_paid_customer",
            {"number": number, "amount": format_tiyin(total), "url": links.order(event.order_id)},
        )
        for sub in event.sub_orders:
            await notifier.notify(
                envelope.event_id,
                sub.seller_id,
                "order_paid_seller",
                {
                    "number": number,
                    "items": sum(item.qty for item in sub.items),
                    "amount": format_tiyin(sub.subtotal_tiyin),
                    "url": links.seller_order(sub.id),
                },
            )

    @router.on(EventType.ORDER_EXPIRED)
    async def on_order_expired(envelope: EventEnvelope) -> None:
        event = OrderExpired.model_validate(envelope.payload)
        await to_customer_of(
            envelope,
            event.order_id,
            "order_expired",
            {"number": order_number(event.order_id), "url": links.order(event.order_id)},
        )

    @router.on(EventType.ORDER_CANCELLED)
    async def on_order_cancelled(envelope: EventEnvelope) -> None:
        event = OrderCancelled.model_validate(envelope.payload)
        await to_customer_of(
            envelope,
            event.order_id,
            "order_cancelled",
            {
                "number": order_number(event.order_id),
                "reason": CANCEL_REASONS.get(event.reason, ""),
                "url": links.order(event.order_id),
            },
        )

    @router.on(EventType.PAYMENT_REFUNDED)
    async def on_payment_refunded(envelope: EventEnvelope) -> None:
        event = PaymentRefunded.model_validate(envelope.payload)
        await to_customer_of(
            envelope,
            event.order_id,
            "payment_refunded",
            {
                "number": order_number(event.order_id),
                "amount": format_tiyin(event.amount_tiyin),
                "url": links.order(event.order_id),
            },
        )

    @router.on(EventType.SUB_ORDER_STATUS_CHANGED)
    async def on_sub_order_status_changed(envelope: EventEnvelope) -> None:
        event = SubOrderStatusChanged.model_validate(envelope.payload)
        texts = SUB_ORDER_TEXTS.get(event.status)
        if texts is None:
            return
        status, text = texts
        await notifier.notify(
            envelope.event_id,
            event.customer_id,
            "sub_order_status",
            {
                "number": order_number(event.order_id),
                "status": status,
                "text": text,
                "url": links.order(event.order_id),
            },
        )

    @router.on(EventType.SELLER_APPROVED)
    async def on_seller_approved(envelope: EventEnvelope) -> None:
        event = SellerApproved.model_validate(envelope.payload)
        await notifier.notify(
            envelope.event_id,
            event.user_id,
            "seller_approved",
            {"shop_name": event.shop_name, "url": links.seller_home()},
        )

    return router


class NotificationEventHandler:
    """What the broker consumer calls for each delivery."""

    def __init__(self, router: EventRouter) -> None:
        self._router = router

    async def __call__(self, body: bytes) -> Outcome:
        return await self._router.dispatch(body)
