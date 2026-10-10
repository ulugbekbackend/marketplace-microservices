"""Payment against the running stack: every Payme and Click simulator scenario, the DoD
check that a repeated webhook never writes the money twice, refunds when a seller cancels,
and the weekly payout of a delivered sub-order.

Run with `make test-integration` after `make up`. Needs PAYME_KEY, CLICK_SERVICE_ID and
CLICK_SECRET_KEY in .env (the payment service reads the same values).
"""

import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from click_simulator import run as run_click
from payme_simulator import PaymeClient, new_tx_id, now_ms
from payme_simulator import run as run_payme
from simulator_kit import ROOT, Order, Shopper
from test_saga import GATEWAY, EventTap, broker_url, env, wait_until
from test_search_sync import Seller

from contracts.enums import EventType
from py_common.demo import SELLERS

PAYME_KEY = env("PAYME_KEY", default="")
CLICK_SERVICE_ID = env("CLICK_SERVICE_ID", default="")
CLICK_SECRET_KEY = env("CLICK_SECRET_KEY", default="")

pytestmark = pytest.mark.skipif(
    not (PAYME_KEY and CLICK_SERVICE_ID and CLICK_SECRET_KEY),
    reason="payment provider keys are not set in .env",
)


@pytest.fixture(scope="module")
def tap() -> Iterator[EventTap]:
    with EventTap(broker_url()) as event_tap:
        yield event_tap


def test_payme_simulator_scenarios() -> None:
    report = run_payme(GATEWAY, PAYME_KEY)

    assert report.ok, report.render()


def test_click_simulator_scenarios() -> None:
    report = run_click(GATEWAY, CLICK_SERVICE_ID, CLICK_SECRET_KEY)

    assert report.ok, report.render()


def test_repeated_perform_publishes_one_payment(tap: EventTap) -> None:
    shopper = Shopper(GATEWAY)
    try:
        payme = PaymeClient(shopper.http, PAYME_KEY)
        order = shopper.reserved_order()
        tx = new_tx_id()
        created = payme.call(
            "CreateTransaction",
            {
                "id": tx,
                "time": now_ms(),
                "amount": order.total_tiyin,
                "account": {"order_id": order.id},
            },
        )
        assert created["result"]["state"] == 1, created

        answers = [payme.call("PerformTransaction", {"id": tx}) for _ in range(3)]

        assert {answer["result"]["state"] for answer in answers} == {2}
        paid = tap.wait_for(EventType.PAYMENT_PAID, order.id)
        assert paid.payload["amount_tiyin"] == order.total_tiyin
        shopper.wait_status(order.id, "PAID")
        time.sleep(2)  # anything published twice would have arrived by now
        assert len(tap.of(EventType.PAYMENT_PAID, order.id)) == 1
        assert len(tap.of(EventType.ORDER_PAID, order.id)) == 1
    finally:
        shopper.close()


# --- refunds and payouts ------------------------------------------------------------------

SHOP = SELLERS[2]


@pytest.fixture(scope="module")
def seller() -> Iterator[Seller]:
    account = Seller(SHOP.phone)
    yield account
    account.http.close()


@pytest.fixture(scope="module")
def buyer() -> Iterator[Shopper]:
    account = Shopper(GATEWAY)
    yield account
    account.close()


def pay(buyer: Shopper, order: Order) -> None:
    payme = PaymeClient(buyer.http, PAYME_KEY)
    tx = new_tx_id()
    payme.call(
        "CreateTransaction",
        {
            "id": tx,
            "time": now_ms(),
            "amount": order.total_tiyin,
            "account": {"order_id": order.id},
        },
    )
    assert payme.call("PerformTransaction", {"id": tx})["result"]["state"] == 2
    buyer.wait_status(order.id, "PAID")


def sub_order_of(seller: Seller, order_id: str) -> dict[str, Any]:
    rows = seller.http.get("/api/orders/seller/", params={"page_size": 50}).json()["items"]
    [row] = [row for row in rows if row["order_id"] == order_id]
    return dict(row)


def set_status(seller: Seller, sub_order_id: str, status: str, **extra: str) -> None:
    response = seller.http.patch(
        f"/api/orders/seller/{sub_order_id}/status/", json={"status": status, **extra}
    )
    assert response.status_code == 200, response.text


def this_week_payout(seller: Seller) -> dict[str, Any] | None:
    items = seller.http.get("/api/payments/seller/payouts/").json()["items"]
    monday = datetime.now(UTC).date().isoformat()
    for item in items:
        if item["period_start"] <= monday < item["period_end"]:
            return dict(item)
    return None


def build_this_weeks_payouts() -> None:
    subprocess.run(
        [
            "docker", "compose", "-f", "infra/docker-compose.yml", "--env-file", ".env",
            "exec", "-T", "payment", "python", "-m", "app.payouts", "run",
            "--week", datetime.now(UTC).date().isoformat(),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )  # fmt: skip


def test_seller_cancel_refunds_the_customer(tap: EventTap, seller: Seller, buyer: Shopper) -> None:
    order = buyer.reserved_order(SHOP.shop_name)
    pay(buyer, order)
    sub_order = sub_order_of(seller, order.id)

    set_status(seller, sub_order["id"], "CANCELLED_BY_SELLER", reason="Out of stock")

    refunded = tap.wait_for(EventType.PAYMENT_REFUNDED, order.id)
    assert refunded.payload["amount_tiyin"] == sub_order["subtotal_tiyin"]
    assert buyer.wait_status(order.id, "REFUNDED")["status"] == "REFUNDED"


def test_delivered_sub_order_joins_the_weekly_payout(seller: Seller, buyer: Shopper) -> None:
    before = this_week_payout(seller)
    order = buyer.reserved_order(SHOP.shop_name)
    pay(buyer, order)
    sub_order = sub_order_of(seller, order.id)
    set_status(seller, sub_order["id"], "ACCEPTED")
    set_status(seller, sub_order["id"], "SHIPPED", tracking_number="TRK-SIM-1")
    set_status(seller, sub_order["id"], "DELIVERED")
    net_before = before["net_tiyin"] if before else 0
    lines_before = before["lines_count"] if before else 0

    def payout_with_the_line() -> dict[str, Any] | None:
        # The DELIVERED event reaches the payment consumer asynchronously: build the week's
        # payouts until the line has joined (the command only adds new lines).
        build_this_weeks_payouts()
        payout = this_week_payout(seller)
        return payout if payout and payout["lines_count"] > lines_before else None

    after = wait_until(payout_with_the_line, "the delivered sub-order in this week's payout")
    assert after["net_tiyin"] - net_before == sub_order["net_tiyin"]
    assert after["lines_count"] - lines_before == 1
    assert after["status"] == "pending"
