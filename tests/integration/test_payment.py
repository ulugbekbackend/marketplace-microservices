"""Payment against the running stack: every Payme and Click simulator scenario, and the
DoD check that a repeated webhook never writes the money twice.

Run with `make test-integration` after `make up`. Needs PAYME_KEY, CLICK_SERVICE_ID and
CLICK_SECRET_KEY in .env (the payment service reads the same values).
"""

import time
from collections.abc import Iterator

import pytest
from click_simulator import run as run_click
from payme_simulator import PaymeClient, new_tx_id, now_ms
from payme_simulator import run as run_payme
from simulator_kit import Shopper
from test_saga import GATEWAY, EventTap, broker_url, env

from contracts.enums import EventType

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
