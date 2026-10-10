"""Check the overselling run: exactly ``stock`` orders PAID, everyone else cancelled or
refused at checkout, the variant sold out with nothing left reserved, no 5xx.

    uv run python tests/load/verify.py        (exit code 1 when a rule is broken)
"""

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tests" / "load" / "results"
GATEWAY = "http://127.0.0.1"


def client(access: str) -> httpx.Client:
    return httpx.Client(
        base_url=GATEWAY,
        headers={"Host": "api.localhost", "Authorization": f"Bearer {access}"},
        timeout=15,
    )


def outcome_of(access: str, started_at: float) -> str:
    """The status of this customer's order from this run, or REFUSED when none was made."""
    with client(access) as http:
        page = http.get("/api/orders/", params={"page_size": 5}).json()
    recent = [
        order
        for order in page["items"]
        if datetime.fromisoformat(order["created_at"]).timestamp() >= started_at
    ]
    return str(recent[0]["status"]) if recent else "REFUSED"


def variant_state(setup: dict[str, Any]) -> dict[str, int]:
    with client(setup["seller"]) as http:
        product = http.get(f"/api/catalog/seller/products/{setup['product_id']}/").json()
    [variant] = [v for v in product["variants"] if v["id"] == setup["variant_id"]]
    return {"stock": int(variant["stock"]), "reserved": int(variant["reserved"])}


def main() -> int:
    setup = json.loads((RESULTS / "setup.json").read_text(encoding="utf-8"))
    summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    outcomes = Counter(outcome_of(token, setup["started_at"]) for token in setup["customers"])
    state = variant_state(setup)
    server_errors = int(
        summary["metrics"].get("server_errors", {}).get("values", {}).get("count", 0)
    )
    p95 = summary["metrics"]["http_req_duration"]["values"]["p(95)"]
    buyers = len(setup["customers"])
    stock = int(setup["stock"])

    rules = {
        f"PAID == {stock}": outcomes["PAID"] == stock,
        f"CANCELLED + REFUSED == {buyers - stock}": outcomes["CANCELLED"] + outcomes["REFUSED"]
        == buyers - stock,
        "stock == 0": state["stock"] == 0,
        "reserved == 0": state["reserved"] == 0,
        "5xx == 0": server_errors == 0,
    }
    report = {
        "buyers": buyers,
        "stock": stock,
        "outcomes": dict(outcomes),
        "variant": state,
        "server_errors": server_errors,
        "p95_ms": round(p95, 1),
        "rules": rules,
    }
    (RESULTS / "verify.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(rules.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
