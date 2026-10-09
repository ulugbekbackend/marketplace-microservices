"""Payme simulator: sends the Merchant API calls Payme would send and checks every answer.

happy                 Check -> Create -> Perform -> CheckTransaction, order becomes PAID
duplicate-create      the same Create twice returns the same transaction
duplicate-perform     Perform twice: one payment, the same perform_time
wrong-amount          Check with another amount is -31001
expired-order         Check for an EXPIRED order is -31051
cancel-after-perform  Cancel a paid transaction: state -2, the order is REFUNDED
bad-auth              a wrong key is -32504
unknown-order         Check for an order that does not exist is -31050
"""

import base64
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from simulator_kit import Order, Report, Shopper, expire_now

MERCHANT_PATH = "/api/payments/payme/merchant"


class PaymeClient:
    def __init__(self, http: httpx.Client, key: str) -> None:
        self._http = http
        self._key = key
        self._next_id = 0

    def call(
        self, method: str, params: dict[str, Any], *, key: str | None = None
    ) -> dict[str, Any]:
        self._next_id += 1
        token = base64.b64encode(f"Paycom:{self._key if key is None else key}".encode()).decode()
        response = self._http.post(
            MERCHANT_PATH,
            json={"id": self._next_id, "method": method, "params": params},
            headers={"Authorization": f"Basic {token}"},
        )
        body: dict[str, Any] = response.json()
        return body


def now_ms() -> int:
    return int(time.time() * 1000)


def code(answer: dict[str, Any]) -> Any:
    return answer.get("error", {}).get("code")


def state(answer: dict[str, Any]) -> Any:
    return answer.get("result", {}).get("state")


@dataclass
class Context:
    payme: PaymeClient
    shopper: Shopper
    report: Report

    def create(self, order: Order, tx_id: str) -> dict[str, Any]:
        return self.payme.call(
            "CreateTransaction",
            {
                "id": tx_id,
                "time": now_ms(),
                "amount": order.total_tiyin,
                "account": {"order_id": order.id},
            },
        )


def new_tx_id() -> str:
    return uuid.uuid4().hex[:24]


def happy(ctx: Context) -> None:
    name, order, tx = "happy", ctx.shopper.reserved_order(), new_tx_id()
    checked = ctx.payme.call(
        "CheckPerformTransaction",
        {"amount": order.total_tiyin, "account": {"order_id": order.id}},
    )
    ctx.report.expect(name, "CheckPerformTransaction", {"allow": True}, checked.get("result"))
    ctx.report.expect(name, "CreateTransaction state", 1, state(ctx.create(order, tx)))
    performed = ctx.payme.call("PerformTransaction", {"id": tx})
    ctx.report.expect(name, "PerformTransaction state", 2, state(performed))
    checked_tx = ctx.payme.call("CheckTransaction", {"id": tx})
    ctx.report.expect(name, "CheckTransaction state", 2, state(checked_tx))
    paid = ctx.shopper.wait_status(order.id, "PAID")
    ctx.report.expect(name, "order status", "PAID", paid["status"])


def duplicate_create(ctx: Context) -> None:
    name, order, tx = "duplicate-create", ctx.shopper.reserved_order(), new_tx_id()
    first, second = ctx.create(order, tx), ctx.create(order, tx)
    ctx.report.expect(name, "same transaction", first.get("result"), second.get("result"))
    other = ctx.create(order, new_tx_id())
    ctx.report.expect(name, "another id for the order", -31052, code(other))
    ctx.payme.call("CancelTransaction", {"id": tx, "reason": 3})


def duplicate_perform(ctx: Context) -> None:
    name, order, tx = "duplicate-perform", ctx.shopper.reserved_order(), new_tx_id()
    ctx.create(order, tx)
    first = ctx.payme.call("PerformTransaction", {"id": tx})
    second = ctx.payme.call("PerformTransaction", {"id": tx})
    ctx.report.expect(name, "same perform result", first.get("result"), second.get("result"))
    paid = ctx.shopper.wait_status(order.id, "PAID")
    transitions = [h["to_status"] for h in paid.get("history", []) if h["to_status"] == "PAID"]
    ctx.report.expect(name, "order paid once", ["PAID"], transitions)


def wrong_amount(ctx: Context) -> None:
    order = ctx.shopper.reserved_order()
    answer = ctx.payme.call(
        "CheckPerformTransaction",
        {"amount": order.total_tiyin + 100, "account": {"order_id": order.id}},
    )
    ctx.report.expect("wrong-amount", "CheckPerformTransaction", -31001, code(answer))


def expired_order(ctx: Context) -> None:
    order = ctx.shopper.reserved_order()
    expire_now(order.id)
    ctx.shopper.wait_status(order.id, "EXPIRED")
    answer = ctx.payme.call(
        "CheckPerformTransaction",
        {"amount": order.total_tiyin, "account": {"order_id": order.id}},
    )
    ctx.report.expect("expired-order", "CheckPerformTransaction", -31051, code(answer))


def cancel_after_perform(ctx: Context) -> None:
    name, order, tx = "cancel-after-perform", ctx.shopper.reserved_order(), new_tx_id()
    ctx.create(order, tx)
    ctx.payme.call("PerformTransaction", {"id": tx})
    ctx.shopper.wait_status(order.id, "PAID")
    cancelled = ctx.payme.call("CancelTransaction", {"id": tx, "reason": 5})
    ctx.report.expect(name, "CancelTransaction state", -2, state(cancelled))
    refunded = ctx.shopper.wait_status(order.id, "REFUNDED")
    ctx.report.expect(name, "order status", "REFUNDED", refunded["status"])


def bad_auth(ctx: Context) -> None:
    answer = ctx.payme.call("CheckTransaction", {"id": new_tx_id()}, key="not-the-key")
    ctx.report.expect("bad-auth", "any method", -32504, code(answer))


def unknown_order(ctx: Context) -> None:
    answer = ctx.payme.call(
        "CheckPerformTransaction", {"amount": 100_000, "account": {"order_id": str(uuid.uuid4())}}
    )
    ctx.report.expect("unknown-order", "CheckPerformTransaction", -31050, code(answer))


SCENARIOS: dict[str, Callable[[Context], None]] = {
    "happy": happy,
    "duplicate-create": duplicate_create,
    "duplicate-perform": duplicate_perform,
    "wrong-amount": wrong_amount,
    "expired-order": expired_order,
    "cancel-after-perform": cancel_after_perform,
    "bad-auth": bad_auth,
    "unknown-order": unknown_order,
}


def run(gateway: str, key: str, names: list[str] | None = None) -> Report:
    """Run the named scenarios (all by default) against the gateway."""
    report = Report()
    shopper = Shopper(gateway)
    try:
        context = Context(PaymeClient(shopper.http, key), shopper, report)
        for name in names or list(SCENARIOS):
            SCENARIOS[name](context)
    finally:
        shopper.close()
    return report
