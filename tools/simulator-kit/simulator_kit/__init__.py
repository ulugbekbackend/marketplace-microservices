"""What both payment simulators need: a logged in shopper on the gateway who can put a
RESERVED order on the table, and a report of expected vs actual answers.

The stack must run with DEBUG=True (the dev OTP master code) and seeded products.
"""

import random
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[3]
API_HOST = {"Host": "api.localhost"}
MASTER_CODE = "000000"
ADDRESS = {
    "full_name": "Simulator",
    "phone": "+998901234567",
    "region": "Toshkent",
    "city": "Toshkent",
    "street": "Amir Temur 1",
}


class SimulatorError(RuntimeError):
    """The stack is not in a state the simulator can work with."""


def wait_until(probe: Callable[[], Any], what: str, timeout: float = 20.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(0.2)
    raise SimulatorError(f"timed out waiting for {what}")


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    total_tiyin: int


class Shopper:
    """A customer logged in through the gateway (OTP with the dev master code)."""

    def __init__(self, gateway: str) -> None:
        self.http = httpx.Client(base_url=gateway, headers=API_HOST, timeout=10)
        phone = f"+99890{random.randint(1_000_000, 9_999_999)}"
        if self._otp("send/", {"phone": phone}).status_code != 204:
            raise SimulatorError("OTP send failed: is the stack up?")
        verified = self._otp("verify/", {"phone": phone, "code": MASTER_CODE})
        if verified.status_code != 200:
            raise SimulatorError(f"OTP verify failed ({verified.status_code}): DEBUG must be on")
        self.http.headers["Authorization"] = f"Bearer {verified.json()['access']}"

    def close(self) -> None:
        self.http.close()

    def _otp(self, path: str, body: dict[str, str]) -> httpx.Response:
        """The gateway allows 5 OTP calls a minute per address: wait out a 429."""
        response = self.http.post(f"/api/auth/otp/{path}", json=body)
        for _ in range(8):
            if response.status_code != 429:
                break
            time.sleep(float(response.headers.get("Retry-After", "13")) + 0.5)
            response = self.http.post(f"/api/auth/otp/{path}", json=body)
        return response

    def in_stock_variant(self) -> str:
        found = self.http.get("/api/search", params={"in_stock": "true", "page_size": 50})
        for product in found.json().get("items", []):
            detail = self.http.get(f"/api/catalog/products/{product['slug']}/").json()
            for variant in detail.get("variants", []):
                if variant.get("available", 0) > 0:
                    return str(variant["id"])
        raise SimulatorError("no product in stock: run `make seed`")

    def reserved_order(self) -> Order:
        """Cart -> checkout -> wait until the catalog reserved the stock."""
        self.http.delete("/api/cart/")
        added = self.http.post(
            "/api/cart/items/", json={"variant_id": self.in_stock_variant(), "qty": 1}
        )
        if added.status_code != 200:
            raise SimulatorError(f"add to cart failed: {added.text}")
        response = self.http.post(
            "/api/orders/checkout/",
            json={"address": ADDRESS},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        if response.status_code != 202:
            raise SimulatorError(f"checkout failed: {response.text}")
        order_id = str(response.json()["order_id"])
        order = self.wait_status(order_id, "RESERVED")
        return Order(id=order_id, total_tiyin=int(order["total_tiyin"]))

    def order(self, order_id: str) -> dict[str, Any]:
        body: dict[str, Any] = self.http.get(f"/api/orders/{order_id}/").json()
        return body

    def wait_status(self, order_id: str, *statuses: str) -> dict[str, Any]:
        def settled() -> dict[str, Any] | None:
            order = self.order(order_id)
            return order if order.get("status") in statuses else None

        result: dict[str, Any] = wait_until(settled, f"order {order_id} in {statuses}")
        return result


def expire_now(order_id: str) -> None:
    """End a reservation through the order service instead of waiting 15 minutes."""
    subprocess.run(
        [
            "docker", "compose", "-f", "infra/docker-compose.yml", "--env-file", ".env",
            "exec", "-T", "order", "python", "manage.py", "expire_orders", "--order", order_id,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )  # fmt: skip


def _cell(value: Any, width: int = 40) -> str:
    text = str(value)
    return text if len(text) <= width else text[: width - 3] + "..."


@dataclass(slots=True)
class Check:
    scenario: str
    step: str
    expected: Any
    actual: Any

    @property
    def ok(self) -> bool:
        return bool(self.expected == self.actual)


@dataclass(slots=True)
class Report:
    checks: list[Check] = field(default_factory=list)

    def expect(self, scenario: str, step: str, expected: Any, actual: Any) -> bool:
        check = Check(scenario, step, expected, actual)
        self.checks.append(check)
        return check.ok

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def failed(self) -> list[Check]:
        return [check for check in self.checks if not check.ok]

    def render(self) -> str:
        rows = [("", "scenario", "step", "expected", "actual")]
        rows += [
            ("ok" if c.ok else "FAIL", c.scenario, c.step, _cell(c.expected), _cell(c.actual))
            for c in self.checks
        ]
        widths = [max(len(row[i]) for row in rows) for i in range(5)]
        lines = [
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
            for row in rows
        ]
        passed = sum(c.ok for c in self.checks)
        lines.append(f"\n{passed}/{len(self.checks)} checks passed")
        return "\n".join(lines)
