"""Set up the overselling load test: one product with 10 units, 100 customers with tokens.

    uv run python tests/load/prepare.py        (make load-test runs it first)

Needs the stack up with DEBUG=True (tokens come from ``manage.py issue_tokens``). Writes
tests/load/results/setup.json for the k6 script and the verification.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tests" / "load" / "results"
GATEWAY = "http://127.0.0.1"
API_HOST = {"Host": "api.localhost"}
SELLER_PHONE = "+998901110002"  # a demo seller from `make seed`
CUSTOMERS = 100
STOCK = 10
PRICE_TIYIN = 50_000_00


def issue_tokens(*args: str) -> list[dict[str, str]]:
    out = subprocess.run(
        [
            "docker", "compose", "-f", "infra/docker-compose.yml", "--env-file", ".env",
            "exec", "-T", "auth", "python", "manage.py", "issue_tokens", *args,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout  # fmt: skip
    tokens: list[dict[str, str]] = json.loads(out.strip().splitlines()[-1])
    return tokens


def client(access: str) -> httpx.Client:
    return httpx.Client(
        base_url=GATEWAY,
        headers={**API_HOST, "Authorization": f"Bearer {access}"},
        timeout=15,
    )


def leaf_category(http: httpx.Client) -> str:
    node: dict[str, Any] = http.get("/api/catalog/categories/").json()[0]
    while node["children"]:
        node = node["children"][0]
    return str(node["id"])


def create_product(seller: httpx.Client) -> dict[str, str]:
    stamp = int(time.time())
    product = seller.post(
        "/api/catalog/seller/products/",
        json={
            "title": f"Load test oxirgi 10 dona {stamp}",
            "description": "",
            "category_id": leaf_category(seller),
            "status": "draft",
        },
    )
    product.raise_for_status()
    product_id = product.json()["id"]
    variant = seller.post(
        f"/api/catalog/seller/products/{product_id}/variants/",
        json={
            "sku": f"LOAD-{stamp}",
            "price_tiyin": PRICE_TIYIN,
            "stock": STOCK,
            "attribute_value_ids": [],
        },
    )
    variant.raise_for_status()
    seller.patch(
        f"/api/catalog/seller/products/{product_id}/", json={"status": "active"}
    ).raise_for_status()
    return {"product_id": product_id, "variant_id": variant.json()["id"]}


def main() -> None:
    [seller] = issue_tokens("--phone", SELLER_PHONE)
    customers = issue_tokens("--customers", str(CUSTOMERS))
    with client(seller["access"]) as http:
        product = create_product(http)
    # Customers are reused between runs: start every one with an empty cart.
    for customer in customers:
        with client(customer["access"]) as http:
            http.delete("/api/cart/")
    RESULTS.mkdir(parents=True, exist_ok=True)
    setup = {
        **product,
        "stock": STOCK,
        "seller": seller["access"],
        "customers": [c["access"] for c in customers],
        "started_at": time.time(),
    }
    (RESULTS / "setup.json").write_text(json.dumps(setup), encoding="utf-8")
    print(f"variant {product['variant_id']}: {STOCK} units, {len(customers)} customers ready")


if __name__ == "__main__":
    main()
