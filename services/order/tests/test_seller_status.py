"""Seller status changes: the transition table over HTTP, validation, the order roll-up,
history and outbox rows."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from rest_framework.test import APIClient

from contracts.enums import EventType, OrderStatus, SubOrderStatus, UserRole
from contracts.events import OrderRefundRequested, SubOrderStatusChanged
from messaging.models import Outbox
from messaging.outbox import to_envelope
from orders import fulfilment
from orders.models import Order, OrderStatusHistory, SubOrder, SubOrderStatusHistory
from tests.conftest import user_client
from tests.factories import make_order, make_paid_order, make_sub_order

pytestmark = pytest.mark.django_db

SS = SubOrderStatus

ALLOWED = {
    (SS.NEW, SS.ACCEPTED),
    (SS.NEW, SS.CANCELLED_BY_SELLER),
    (SS.ACCEPTED, SS.SHIPPED),
    (SS.ACCEPTED, SS.CANCELLED_BY_SELLER),
    (SS.SHIPPED, SS.DELIVERED),
}
TARGETS = [SS.ACCEPTED, SS.SHIPPED, SS.DELIVERED, SS.CANCELLED_BY_SELLER]
EVERY_PAIR = [(source, target) for source in SS for target in TARGETS]


@pytest.fixture
def seller_id() -> UUID:
    return uuid4()


@pytest.fixture
def seller_api(seller_id: UUID) -> APIClient:
    client = user_client(seller_id, UserRole.SELLER)
    client.credentials(
        HTTP_X_USER_ID=str(seller_id),
        HTTP_X_USER_ROLE=UserRole.SELLER.value,
        HTTP_X_SELLER_ID=str(seller_id),
    )
    return client


def body_for(target: SubOrderStatus) -> dict[str, Any]:
    body: dict[str, Any] = {"status": target.value}
    if target is SS.SHIPPED:
        body["tracking_number"] = "UZ123456789"
    if target is SS.CANCELLED_BY_SELLER:
        body["reason"] = "Out of stock in the warehouse"
    return body


def patch(client: APIClient, sub_order: SubOrder, body: dict[str, Any]) -> Any:
    return client.patch(f"/api/orders/seller/{sub_order.id}/status/", body, format="json")


def events(event_type: EventType) -> list[Any]:
    return [to_envelope(row) for row in Outbox.objects.filter(event_type=event_type.value)]


@pytest.mark.parametrize(("source", "target"), EVERY_PAIR)
def test_every_transition_over_http(
    seller_api: APIClient, seller_id: UUID, source: SubOrderStatus, target: SubOrderStatus
) -> None:
    order_status = OrderStatus.FULFILLING if source is SS.SHIPPED else OrderStatus.PAID
    sub_order = make_sub_order(seller_id, status=source, order_status=order_status)

    response = patch(seller_api, sub_order, body_for(target))

    sub_order.refresh_from_db()
    if (source, target) in ALLOWED:
        assert response.status_code == 200
        assert response.json()["status"] == target.value
        assert sub_order.status == target.value
        assert len(events(EventType.SUB_ORDER_STATUS_CHANGED)) == 1
    else:
        assert response.status_code == 409
        assert response.json()["error"] == {
            "code": "INVALID_TRANSITION",
            "message": f"Cannot change status from {source.value} to {target.value}.",
            "details": {"from": source.value, "to": target.value},
        }
        assert sub_order.status == source.value
        assert not Outbox.objects.exists()


def test_accept_returns_the_detail_and_writes_history(
    seller_api: APIClient, seller_id: UUID
) -> None:
    sub_order = make_sub_order(seller_id)

    response = patch(seller_api, sub_order, {"status": "ACCEPTED", "reason": "on it"})

    body = response.json()
    assert body["id"] == str(sub_order.id)
    assert body["order_status"] == "PAID"
    assert [(h["from_status"], h["to_status"], h["reason"]) for h in body["history"]] == [
        (None, "NEW", ""),
        ("NEW", "ACCEPTED", "on it"),
    ]


def test_ship_stores_the_tracking_number(seller_api: APIClient, seller_id: UUID) -> None:
    sub_order = make_sub_order(seller_id, status=SS.ACCEPTED)

    response = patch(seller_api, sub_order, {"status": "SHIPPED", "tracking_number": "  UZ-42  "})

    assert response.status_code == 200
    assert response.json()["tracking_number"] == "UZ-42"
    sub_order.refresh_from_db()
    assert sub_order.tracking_number == "UZ-42"


@pytest.mark.parametrize(
    "body",
    [
        {"status": "SHIPPED"},
        {"status": "SHIPPED", "tracking_number": ""},
        {"status": "SHIPPED", "tracking_number": "   "},
        {"status": "SHIPPED", "tracking_number": "X" * 65},
    ],
)
def test_ship_needs_a_tracking_number(
    seller_api: APIClient, seller_id: UUID, body: dict[str, Any]
) -> None:
    sub_order = make_sub_order(seller_id, status=SS.ACCEPTED)

    response = patch(seller_api, sub_order, body)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "tracking_number" in error["details"]
    sub_order.refresh_from_db()
    assert sub_order.status == SS.ACCEPTED.value


@pytest.mark.parametrize(
    "body",
    [
        {"status": "CANCELLED_BY_SELLER"},
        {"status": "CANCELLED_BY_SELLER", "reason": " "},
        {"status": "CANCELLED_BY_SELLER", "reason": "x" * 256},
    ],
)
def test_cancel_needs_a_reason(
    seller_api: APIClient, seller_id: UUID, body: dict[str, Any]
) -> None:
    sub_order = make_sub_order(seller_id)

    response = patch(seller_api, sub_order, body)

    assert response.status_code == 400
    assert "reason" in response.json()["error"]["details"]


@pytest.mark.parametrize("status", ["NEW", "PAID", "", None])
def test_unknown_target_is_400(seller_api: APIClient, seller_id: UUID, status: Any) -> None:
    sub_order = make_sub_order(seller_id)

    response = patch(seller_api, sub_order, {"status": status})

    assert response.status_code == 400
    assert "status" in response.json()["error"]["details"]


def test_cancel_stores_the_reason_and_requests_a_refund(
    seller_api: APIClient, seller_id: UUID
) -> None:
    sub_order = make_sub_order(seller_id, subtotal_tiyin=2_500_000, qty=2, status=SS.ACCEPTED)

    response = patch(seller_api, sub_order, {"status": "CANCELLED_BY_SELLER", "reason": "Damaged"})

    assert response.status_code == 200
    assert response.json()["cancel_reason"] == "Damaged"
    [refund] = events(EventType.ORDER_REFUND_REQUESTED)
    payload = OrderRefundRequested.model_validate(refund.payload)
    assert payload == OrderRefundRequested(
        order_id=sub_order.order_id, amount_tiyin=2_500_000, reason="CANCELLED_BY_SELLER"
    )
    assert refund.correlation_id == sub_order.order_id
    # The only sub-order is cancelled: the order waits for the refund as PAID.
    assert Order.objects.get(id=sub_order.order_id).status == OrderStatus.PAID.value


def test_every_change_publishes_status_changed(seller_api: APIClient, seller_id: UUID) -> None:
    sub_order = make_sub_order(seller_id)
    order = sub_order.order

    for target in (SS.ACCEPTED, SS.SHIPPED, SS.DELIVERED):
        assert patch(seller_api, sub_order, body_for(target)).status_code == 200

    changes = [
        SubOrderStatusChanged.model_validate(e.payload)
        for e in events(EventType.SUB_ORDER_STATUS_CHANGED)
    ]
    assert [c.status for c in changes] == [SS.ACCEPTED, SS.SHIPPED, SS.DELIVERED]
    assert {(c.sub_order_id, c.order_id, c.seller_id, c.customer_id) for c in changes} == {
        (sub_order.id, order.id, seller_id, order.customer_id)
    }
    assert not events(EventType.ORDER_REFUND_REQUESTED)


# --- roll-up ------------------------------------------------------------------------------


def order_history(order: Order) -> list[tuple[str | None, str, str]]:
    return [
        (h.from_status, h.to_status, h.reason)
        for h in OrderStatusHistory.objects.filter(order=order)
    ]


def two_seller_order(seller_id: UUID) -> tuple[Order, SubOrder, SubOrder]:
    other = uuid4()
    order, subs = make_paid_order(lines=[(seller_id, 1_000, 1), (other, 2_000, 1)])
    return order, subs[seller_id], subs[other]


def run(sub_order: SubOrder, *targets: SubOrderStatus) -> None:
    client = user_client(sub_order.seller_id, UserRole.SELLER)
    for target in targets:
        response = patch(client, sub_order, body_for(target))
        assert response.status_code == 200, response.json()


def test_first_shipment_moves_the_order_to_fulfilling(seller_id: UUID) -> None:
    order, mine, other = two_seller_order(seller_id)

    run(mine, SS.ACCEPTED)
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID.value

    run(mine, SS.SHIPPED)
    order.refresh_from_db()
    assert order.status == OrderStatus.FULFILLING.value

    run(other, SS.ACCEPTED, SS.SHIPPED)  # the second shipment changes nothing more
    assert order_history(order) == [
        (None, "PAID", ""),
        ("PAID", "FULFILLING", "SUB_ORDER_SHIPPED"),
    ]


def test_all_delivered_completes_the_order(seller_id: UUID) -> None:
    order, mine, other = two_seller_order(seller_id)

    run(mine, SS.ACCEPTED, SS.SHIPPED, SS.DELIVERED)
    order.refresh_from_db()
    assert order.status == OrderStatus.FULFILLING.value

    run(other, SS.ACCEPTED, SS.SHIPPED, SS.DELIVERED)
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED.value
    assert order_history(order)[-1] == ("FULFILLING", "COMPLETED", "ALL_SUB_ORDERS_DELIVERED")


def test_cancelled_and_delivered_completes_the_order(seller_id: UUID) -> None:
    order, mine, other = two_seller_order(seller_id)

    run(other, SS.CANCELLED_BY_SELLER)
    run(mine, SS.ACCEPTED, SS.SHIPPED, SS.DELIVERED)

    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED.value


def test_cancelling_the_last_open_sub_order_completes_the_order(seller_id: UUID) -> None:
    order, mine, other = two_seller_order(seller_id)
    run(mine, SS.ACCEPTED, SS.SHIPPED, SS.DELIVERED)
    run(other, SS.ACCEPTED)

    run(other, SS.CANCELLED_BY_SELLER)

    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED.value
    [refund] = events(EventType.ORDER_REFUND_REQUESTED)
    assert refund.payload["amount_tiyin"] == 2_000


def test_all_cancelled_leaves_the_order_paid(seller_id: UUID) -> None:
    order, mine, other = two_seller_order(seller_id)

    run(mine, SS.CANCELLED_BY_SELLER)
    run(other, SS.ACCEPTED, SS.CANCELLED_BY_SELLER)

    order.refresh_from_db()
    assert order.status == OrderStatus.PAID.value
    assert order_history(order) == [(None, "PAID", "")]
    assert len(events(EventType.ORDER_REFUND_REQUESTED)) == 2


@pytest.mark.parametrize(
    "order_status", [OrderStatus.COMPLETED, OrderStatus.REFUNDED, OrderStatus.RESERVED]
)
def test_inactive_order_blocks_changes(
    seller_api: APIClient, seller_id: UUID, order_status: OrderStatus
) -> None:
    sub_order = make_sub_order(seller_id, order_status=order_status)

    response = patch(seller_api, sub_order, {"status": "ACCEPTED"})

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "ORDER_NOT_ACTIVE",
        "message": f"The order is {order_status.value}; its sub-orders can no longer change.",
        "details": {"order_status": order_status.value},
    }
    sub_order.refresh_from_db()
    assert sub_order.status == SS.NEW.value
    assert not Outbox.objects.exists()


# --- customer view ------------------------------------------------------------------------


def test_customer_detail_shows_the_sub_order_timeline(seller_id: UUID) -> None:
    customer = uuid4()
    order, subs = make_paid_order(customer_id=customer, lines=[(seller_id, 1_000, 1)])
    run(subs[seller_id], SS.ACCEPTED, SS.SHIPPED)

    body = user_client(customer).get(f"/api/orders/{order.id}/").json()

    [group] = body["sellers"]
    assert group["status"] == "SHIPPED"
    assert group["tracking_number"] == "UZ123456789"
    assert group["cancel_reason"] == ""
    assert [(h["from_status"], h["to_status"]) for h in group["history"]] == [
        (None, "NEW"),
        ("NEW", "ACCEPTED"),
        ("ACCEPTED", "SHIPPED"),
    ]
    assert body["status"] == "FULFILLING"


def test_customer_detail_before_payment_has_empty_sub_order_fields() -> None:
    customer = uuid4()
    order = make_order(customer_id=customer)

    body = user_client(customer).get(f"/api/orders/{order.id}/").json()

    [group] = body["sellers"]
    assert group["tracking_number"] is None
    assert group["cancel_reason"] is None
    assert group["history"] == []


# --- access -------------------------------------------------------------------------------


def test_foreign_sub_order_is_404(seller_api: APIClient) -> None:
    sub_order = make_sub_order(uuid4())

    response = patch(seller_api, sub_order, {"status": "ACCEPTED"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    sub_order.refresh_from_db()
    assert sub_order.status == SS.NEW.value


def test_unknown_sub_order_is_404_even_with_a_bad_body(seller_api: APIClient) -> None:
    response = seller_api.patch(f"/api/orders/seller/{uuid4()}/status/", {}, format="json")

    assert response.status_code == 404


def test_customers_are_403(seller_id: UUID) -> None:
    sub_order = make_sub_order(seller_id)

    response = patch(user_client(seller_id), sub_order, {"status": "ACCEPTED"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_anonymous_is_401(anonymous: APIClient, seller_id: UUID) -> None:
    sub_order = make_sub_order(seller_id)

    response = patch(anonymous, sub_order, {"status": "ACCEPTED"})

    assert response.status_code == 401


def test_change_status_refuses_foreign_sub_orders() -> None:
    sub_order = make_sub_order(uuid4())

    with pytest.raises(fulfilment.SubOrderNotFound) as caught:
        fulfilment.change_status(uuid4(), sub_order.id, SS.ACCEPTED)

    assert caught.value.status_code == 404
    assert str(SubOrderStatusHistory.objects.get(sub_order=sub_order)) == "None -> NEW"
