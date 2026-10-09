"""Click simulator: posts the SHOP API requests Click would post and checks every answer.

happy               prepare -> complete, the order becomes PAID
bad-sign            a wrong sign_string is -1
wrong-amount        another amount is -2
duplicate-complete  complete twice: -4 the second time, one payment
cancelled           Click reports a failure on complete: -9, and -9 again afterwards
unknown-order       an order that does not exist is -5
"""

import hashlib
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from simulator_kit import Order, Report, Shopper

PREPARE_PATH = "/api/payments/click/prepare"
COMPLETE_PATH = "/api/payments/click/complete"


def som(amount_tiyin: int) -> str:
    return f"{Decimal(amount_tiyin) / 100:.2f}"


class ClickClient:
    def __init__(self, http: httpx.Client, service_id: str, secret_key: str) -> None:
        self._http = http
        self._service_id = service_id
        self._secret_key = secret_key

    def _sign(self, form: dict[str, str]) -> str:
        parts = [form["click_trans_id"], form["service_id"], self._secret_key]
        parts.append(form["merchant_trans_id"])
        if "merchant_prepare_id" in form:
            parts.append(form["merchant_prepare_id"])
        parts += [form["amount"], form["action"], form["sign_time"]]
        return hashlib.md5("".join(parts).encode()).hexdigest()

    def _post(self, path: str, form: dict[str, str], *, bad_sign: bool) -> dict[str, Any]:
        form["sign_string"] = "0" * 32 if bad_sign else self._sign(form)
        body: dict[str, Any] = self._http.post(path, data=form).json()
        return body

    def _form(self, click_trans_id: str, order_id: str, amount: str, action: int) -> dict[str, str]:
        return {
            "click_trans_id": click_trans_id,
            "service_id": self._service_id,
            "click_paydoc_id": str(random.randint(10**6, 10**7)),
            "merchant_trans_id": order_id,
            "amount": amount,
            "action": str(action),
            "error": "0",
            "error_note": "Success",
            "sign_time": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def prepare(
        self, click_trans_id: str, order_id: str, amount: str, *, bad_sign: bool = False
    ) -> dict[str, Any]:
        form = self._form(click_trans_id, order_id, amount, 0)
        return self._post(PREPARE_PATH, form, bad_sign=bad_sign)

    def complete(
        self,
        click_trans_id: str,
        order_id: str,
        amount: str,
        prepare_id: Any,
        *,
        error: int = 0,
    ) -> dict[str, Any]:
        form = self._form(click_trans_id, order_id, amount, 1)
        form["merchant_prepare_id"] = str(prepare_id)
        form["error"] = str(error)
        return self._post(COMPLETE_PATH, form, bad_sign=False)


def new_click_id() -> str:
    return str(random.randint(10**9, 10**10))


@dataclass
class Context:
    click: ClickClient
    shopper: Shopper
    report: Report

    def prepared(self, name: str, order: Order) -> tuple[str, Any]:
        click_id = new_click_id()
        answer = self.click.prepare(click_id, order.id, som(order.total_tiyin))
        self.report.expect(name, "prepare", 0, answer.get("error"))
        return click_id, answer.get("merchant_prepare_id")


def paid_once(ctx: Context, name: str, order: Order) -> None:
    paid = ctx.shopper.wait_status(order.id, "PAID")
    transitions = [h["to_status"] for h in paid.get("history", []) if h["to_status"] == "PAID"]
    ctx.report.expect(name, "order paid once", ["PAID"], transitions)


def happy(ctx: Context) -> None:
    name, order = "happy", ctx.shopper.reserved_order()
    click_id, prepare_id = ctx.prepared(name, order)
    done = ctx.click.complete(click_id, order.id, som(order.total_tiyin), prepare_id)
    ctx.report.expect(name, "complete", 0, done.get("error"))
    paid_once(ctx, name, order)


def bad_sign(ctx: Context) -> None:
    order = ctx.shopper.reserved_order()
    answer = ctx.click.prepare(new_click_id(), order.id, som(order.total_tiyin), bad_sign=True)
    ctx.report.expect("bad-sign", "prepare", -1, answer.get("error"))


def wrong_amount(ctx: Context) -> None:
    order = ctx.shopper.reserved_order()
    answer = ctx.click.prepare(new_click_id(), order.id, som(order.total_tiyin + 100))
    ctx.report.expect("wrong-amount", "prepare", -2, answer.get("error"))


def duplicate_complete(ctx: Context) -> None:
    name, order = "duplicate-complete", ctx.shopper.reserved_order()
    click_id, prepare_id = ctx.prepared(name, order)
    amount = som(order.total_tiyin)
    first = ctx.click.complete(click_id, order.id, amount, prepare_id)
    second = ctx.click.complete(click_id, order.id, amount, prepare_id)
    ctx.report.expect(name, "first complete", 0, first.get("error"))
    ctx.report.expect(name, "second complete", -4, second.get("error"))
    paid_once(ctx, name, order)


def cancelled(ctx: Context) -> None:
    name, order = "cancelled", ctx.shopper.reserved_order()
    click_id, prepare_id = ctx.prepared(name, order)
    amount = som(order.total_tiyin)
    failed = ctx.click.complete(click_id, order.id, amount, prepare_id, error=-5017)
    ctx.report.expect(name, "complete with a Click error", -9, failed.get("error"))
    again = ctx.click.complete(click_id, order.id, amount, prepare_id)
    ctx.report.expect(name, "complete afterwards", -9, again.get("error"))


def unknown_order(ctx: Context) -> None:
    answer = ctx.click.prepare(new_click_id(), str(uuid.uuid4()), "1000.00")
    ctx.report.expect("unknown-order", "prepare", -5, answer.get("error"))


SCENARIOS: dict[str, Callable[[Context], None]] = {
    "happy": happy,
    "bad-sign": bad_sign,
    "wrong-amount": wrong_amount,
    "duplicate-complete": duplicate_complete,
    "cancelled": cancelled,
    "unknown-order": unknown_order,
}


def run(gateway: str, service_id: str, secret_key: str, names: list[str] | None = None) -> Report:
    """Run the named scenarios (all by default) against the gateway."""
    report = Report()
    shopper = Shopper(gateway)
    try:
        context = Context(ClickClient(shopper.http, service_id, secret_key), shopper, report)
        for name in names or list(SCENARIOS):
            SCENARIOS[name](context)
    finally:
        shopper.close()
    return report
