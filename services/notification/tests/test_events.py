"""Each event reaches the right people with the right template, once."""

from uuid import UUID, uuid4

import pytest

from contracts.enums import SubOrderStatus
from contracts.events import (
    OrderCancelled,
    OrderExpired,
    OrderItemRef,
    OrderPaid,
    PaymentRefunded,
    SellerApproved,
    StockFailed,
    SubOrderRef,
    SubOrderStatusChanged,
)
from py_common.consumer import EventRouter, Outcome
from tests.conftest import FakeDirectory, Sent, body, texts


def order_number(order_id: UUID) -> str:
    return f"#{str(order_id)[:8].upper()}"


def plain(text: str) -> str:
    return text.replace(chr(0xA0), " ")


async def test_order_paid_tells_the_customer_and_every_seller(
    router: EventRouter, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    customer = fake_directory.add_user(phone="+998900000001", full_name="Aziza")
    seller_a = fake_directory.add_user(phone="+998900000002")
    seller_b = fake_directory.add_user(phone="+998900000003")
    order_id, sub_a, sub_b = uuid4(), uuid4(), uuid4()
    event = OrderPaid(
        order_id=order_id,
        customer_id=customer,
        sub_orders=[
            SubOrderRef(
                id=sub_a,
                seller_id=seller_a,
                items=[OrderItemRef(variant_id=uuid4(), qty=2)],
                subtotal_tiyin=1_000_000_00,
                commission_tiyin=100_000_00,
            ),
            SubOrderRef(
                id=sub_b,
                seller_id=seller_b,
                items=[OrderItemRef(variant_id=uuid4(), qty=1)],
                subtotal_tiyin=250_000_50,
                commission_tiyin=20_000_00,
            ),
        ],
    )

    assert await router.dispatch(body(event)) is Outcome.HANDLED

    assert [sent.contact.phone for sent in outbox] == [
        "+998900000001",
        "+998900000002",
        "+998900000003",
    ]
    customer_sms, seller_a_sms, seller_b_sms = (plain(t) for t in texts(outbox))
    number = order_number(order_id)
    assert outbox[0].message.subject == f"Buyurtma {number} to'landi"
    assert "1 250 000,50 so'm qabul qilindi" in customer_sms
    assert f"http://shop.test/orders/{order_id}" in customer_sms
    assert "2 ta mahsulot, 1 000 000 so'm" in seller_a_sms
    assert f"http://seller.test/orders/{sub_a}" in seller_a_sms
    assert f"http://seller.test/orders/{sub_b}" in seller_b_sms


@pytest.mark.parametrize(
    ("event_for", "subject", "fragment"),
    [
        (
            lambda order_id: OrderExpired(
                order_id=order_id, items=[OrderItemRef(variant_id=uuid4(), qty=1)]
            ),
            "bekor bo'ldi",
            "to'lov vaqtida kelmadi",
        ),
        (
            lambda order_id: OrderCancelled(
                order_id=order_id,
                items=[OrderItemRef(variant_id=uuid4(), qty=1)],
                reason="OUT_OF_STOCK",
            ),
            "bekor qilindi",
            "Mahsulot omborda qolmagan edi.",
        ),
        (
            lambda order_id: PaymentRefunded(order_id=order_id, amount_tiyin=150_000_00),
            "pul qaytarildi",
            "150 000 so'm qaytarildi",
        ),
    ],
)
async def test_order_events_reach_the_customer_found_through_the_order(
    router: EventRouter,
    fake_directory: FakeDirectory,
    outbox: list[Sent],
    event_for: object,
    subject: str,
    fragment: str,
) -> None:
    customer = fake_directory.add_user(phone="+998900000009")
    order_id = uuid4()
    fake_directory.order_owners[order_id] = customer

    await router.dispatch(body(event_for(order_id)))  # type: ignore[operator]

    [sent] = outbox
    assert sent.contact.phone == "+998900000009"
    assert subject in sent.message.subject
    assert fragment in plain(sent.message.text)


async def test_unknown_cancel_reason_leaves_the_reason_out(
    router: EventRouter, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    order_id = uuid4()
    fake_directory.order_owners[order_id] = fake_directory.add_user()

    await router.dispatch(
        body(
            OrderCancelled(
                order_id=order_id, items=[OrderItemRef(variant_id=uuid4(), qty=1)], reason="X"
            )
        )
    )

    assert texts(outbox)[0].startswith(f"Buyurtma {order_number(order_id)} bekor qilindi.\n")


@pytest.mark.parametrize(
    ("status", "words"),
    [
        (SubOrderStatus.ACCEPTED, "qabul qilindi"),
        (SubOrderStatus.SHIPPED, "yo'lda"),
        (SubOrderStatus.DELIVERED, "yetkazildi"),
        (SubOrderStatus.CANCELLED_BY_SELLER, "do'kon bekor qildi"),
    ],
)
async def test_sub_order_progress_is_told_to_the_customer(
    router: EventRouter,
    fake_directory: FakeDirectory,
    outbox: list[Sent],
    status: SubOrderStatus,
    words: str,
) -> None:
    customer = fake_directory.add_user()
    order_id = uuid4()
    event = SubOrderStatusChanged(
        sub_order_id=uuid4(),
        order_id=order_id,
        seller_id=uuid4(),
        customer_id=customer,
        status=status,
    )

    await router.dispatch(body(event))

    [sent] = outbox
    assert sent.message.subject == f"Buyurtma {order_number(order_id)}: {words}"


async def test_a_new_sub_order_is_not_announced_twice(
    router: EventRouter, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    event = SubOrderStatusChanged(
        sub_order_id=uuid4(),
        order_id=uuid4(),
        seller_id=uuid4(),
        customer_id=fake_directory.add_user(),
        status=SubOrderStatus.NEW,
    )

    assert await router.dispatch(body(event)) is Outcome.HANDLED
    assert outbox == []


async def test_seller_approval_is_told_to_the_seller(
    router: EventRouter, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    seller = fake_directory.add_user(phone="+998900000077")

    await router.dispatch(body(SellerApproved(user_id=seller, shop_name="Rishton sopol")))

    [sent] = outbox
    assert sent.message.subject == "Do'koningiz tasdiqlandi"
    assert '"Rishton sopol" do\'koni tasdiqlandi' in sent.message.text
    assert "http://seller.test/" in sent.message.text


async def test_a_redelivered_event_is_sent_once(
    router: EventRouter, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    raw = body(SellerApproved(user_id=fake_directory.add_user(), shop_name="Do'kon"))

    assert await router.dispatch(raw) is Outcome.HANDLED
    assert await router.dispatch(raw) is Outcome.DUPLICATE
    assert len(outbox) == 1


async def test_unknown_order_or_user_is_skipped(
    router: EventRouter, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    assert (
        await router.dispatch(
            body(OrderExpired(order_id=uuid4(), items=[OrderItemRef(variant_id=uuid4(), qty=1)]))
        )
        is Outcome.HANDLED
    )
    assert (
        await router.dispatch(body(SellerApproved(user_id=uuid4(), shop_name="X")))
        is Outcome.HANDLED
    )
    assert outbox == []


async def test_directory_failure_is_retried_later(
    router: EventRouter, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    seller = fake_directory.add_user()
    raw = body(SellerApproved(user_id=seller, shop_name="Do'kon"))
    fake_directory.mode = "down"

    with pytest.raises(RuntimeError):
        await router.dispatch(raw)

    # The failed attempt released the event: the broker's redelivery is handled.
    fake_directory.mode = "ok"
    assert await router.dispatch(raw) is Outcome.HANDLED
    assert len(outbox) == 1


async def test_other_events_are_ignored(router: EventRouter) -> None:
    assert await router.dispatch(body(StockFailed(order_id=uuid4(), reason="x"))) is Outcome.IGNORED
