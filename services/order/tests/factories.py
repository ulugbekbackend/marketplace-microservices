"""Model factories. Tests call the typed ``make_*`` helpers."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from django.utils import timezone
from factory.declarations import LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory

from contracts.enums import OrderStatus, SubOrderStatus
from contracts.money import apply_commission
from orders.models import Order, OrderItem, OrderStatusHistory, SubOrder, SubOrderStatusHistory

ADDRESS = {
    "full_name": "Aziz Karimov",
    "phone": "+998901234567",
    "region": "Toshkent",
    "city": "Toshkent",
    "street": "Amir Temur 1",
    "notes": "",
}


class OrderFactory(DjangoModelFactory[Order]):
    class Meta:
        model = Order

    customer_id = LazyFunction(uuid4)  # type: ignore[no-untyped-call]
    status = OrderStatus.RESERVED.value
    total_tiyin = 0
    delivery_address = ADDRESS
    reserved_until = LazyFunction(  # type: ignore[no-untyped-call]
        lambda: timezone.now() + timedelta(minutes=15)
    )


class OrderItemFactory(DjangoModelFactory[OrderItem]):
    class Meta:
        model = OrderItem

    order = SubFactory(OrderFactory)  # type: ignore[no-untyped-call]
    variant_id = LazyFunction(uuid4)  # type: ignore[no-untyped-call]
    seller_id = LazyFunction(uuid4)  # type: ignore[no-untyped-call]
    shop_name_snapshot = "Tech Shop"
    title_snapshot = Sequence(lambda n: f"Product {n}")  # type: ignore[no-untyped-call]
    sku_snapshot = Sequence(lambda n: f"SKU-{n:05d}")  # type: ignore[no-untyped-call]
    image_snapshot = ""
    price_snapshot_tiyin = 1_000_000
    qty = 1


def make_order(
    *,
    customer_id: UUID | None = None,
    status: OrderStatus = OrderStatus.RESERVED,
    reserved_until: datetime | None = None,
    lines: list[tuple[UUID, int, int]] | None = None,
    **fields: Any,
) -> Order:
    """An order with items; ``lines`` are (seller_id, price_tiyin, qty)."""
    lines = lines if lines is not None else [(uuid4(), 1_000_000, 1)]
    if reserved_until is None and status is OrderStatus.RESERVED:
        reserved_until = timezone.now() + timedelta(minutes=15)
    order = OrderFactory.create(
        customer_id=customer_id or uuid4(),
        status=status.value,
        reserved_until=reserved_until,
        total_tiyin=sum(price * qty for _, price, qty in lines),
        **fields,
    )
    for seller_id, price, qty in lines:
        OrderItemFactory.create(
            order=order, seller_id=seller_id, price_snapshot_tiyin=price, qty=qty
        )
    OrderStatusHistory.objects.create(order=order, from_status=None, to_status=status.value)
    return order


def add_sub_order(
    order: Order,
    seller_id: UUID,
    *,
    status: SubOrderStatus = SubOrderStatus.NEW,
    rate: str = "0.1000",
    created_at: datetime | None = None,
) -> SubOrder:
    """The sub-order of ``seller_id`` over its items of ``order``, as payment creates it."""
    lines = list(order.items.filter(seller_id=seller_id))
    subtotal = sum(line.line_total_tiyin for line in lines)
    sub_order = SubOrder.objects.create(
        order=order,
        seller_id=seller_id,
        status=status.value,
        subtotal_tiyin=subtotal,
        commission_rate_snapshot=Decimal(rate),
        commission_tiyin=apply_commission(subtotal, Decimal(rate)),
    )
    OrderItem.objects.filter(id__in=[line.id for line in lines]).update(sub_order=sub_order)
    SubOrderStatusHistory.objects.create(sub_order=sub_order, from_status=None, to_status=status)
    if created_at is not None:
        SubOrder.objects.filter(id=sub_order.id).update(created_at=created_at)
        sub_order.refresh_from_db()
    return sub_order


def make_paid_order(
    *,
    lines: list[tuple[UUID, int, int]],
    customer_id: UUID | None = None,
    status: OrderStatus = OrderStatus.PAID,
    **fields: Any,
) -> tuple[Order, dict[UUID, SubOrder]]:
    """A paid order split per seller; returns the order and its sub-orders by seller."""
    order = make_order(customer_id=customer_id, status=status, lines=lines, **fields)
    sellers = dict.fromkeys(seller_id for seller_id, _, _ in lines)
    return order, {seller_id: add_sub_order(order, seller_id) for seller_id in sellers}


def make_sub_order(
    seller_id: UUID,
    *,
    subtotal_tiyin: int = 1_000_000,
    qty: int = 1,
    status: SubOrderStatus = SubOrderStatus.NEW,
    rate: str = "0.1000",
    created_at: datetime | None = None,
    order_status: OrderStatus = OrderStatus.PAID,
    **fields: Any,
) -> SubOrder:
    """A one-seller paid order and its sub-order."""
    order = make_order(
        status=order_status, lines=[(seller_id, subtotal_tiyin // qty, qty)], **fields
    )
    return add_sub_order(order, seller_id, status=status, rate=rate, created_at=created_at)
