"""Model factories. Tests call the typed ``make_*`` helpers."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from django.utils import timezone
from factory.declarations import LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory

from contracts.enums import OrderStatus
from orders.models import Order, OrderItem, OrderStatusHistory

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
