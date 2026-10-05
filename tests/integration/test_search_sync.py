"""Search follows the catalog through events: a new product is findable within seconds.

Run with `make test-integration` after `make up` (seed data loaded).
"""

import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from test_saga import Shopper

from py_common.demo import SELLERS

#: Phase P4 definition of done: a new product shows up in search within 10 seconds.
SEARCH_DEADLINE_SECONDS = 10


class Seller(Shopper):
    """A seed seller: logs in with the seller's phone instead of a random one."""

    def __init__(self, phone: str) -> None:
        self._phone = phone
        super().__init__()

    def _otp(self, path: str, body: dict[str, str]) -> httpx.Response:
        return super()._otp(path, {**body, "phone": self._phone})


def leaf_category(tree: list[dict[str, Any]]) -> dict[str, Any]:
    node = tree[0]
    while node["children"]:
        node = node["children"][0]
    return node


def seconds_until_found(http: httpx.Client, query: str, *, present: bool) -> float:
    start = time.monotonic()
    while time.monotonic() - start < SEARCH_DEADLINE_SECONDS * 3:
        found = http.get("/api/search", params={"q": query}).json()["total"] > 0
        if found is present:
            return time.monotonic() - start
        time.sleep(0.2)
    raise AssertionError(f"search did not {'find' if present else 'drop'} {query!r}")


@pytest.fixture(scope="module")
def seller() -> Iterator[Seller]:
    account = Seller(SELLERS[1].phone)
    yield account
    account.http.close()


def test_new_product_is_searchable_within_ten_seconds(seller: Seller) -> None:
    http = seller.http
    token = f"dodsearch{uuid.uuid4().hex[:8]}"
    category = leaf_category(http.get("/api/catalog/categories/").json())

    created = http.post(
        "/api/catalog/seller/products/",
        json={"title": f"Qidiruv sinovi {token}", "category_id": category["id"]},
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    variant = http.post(
        f"/api/catalog/seller/products/{product_id}/variants/",
        json={"sku": token.upper(), "price_tiyin": 1_500_000, "stock": 3},
    )
    assert variant.status_code == 201, variant.text

    activated = http.patch(f"/api/catalog/seller/products/{product_id}/", json={"status": "active"})
    assert activated.status_code == 200, activated.text
    appeared_after = seconds_until_found(http, token, present=True)

    hit = http.get("/api/search", params={"q": token}).json()["items"][0]
    assert hit["id"] == product_id
    assert hit["min_price"] == 1_500_000 and hit["in_stock"] is True

    archived = http.patch(
        f"/api/catalog/seller/products/{product_id}/", json={"status": "archived"}
    )
    assert archived.status_code == 200, archived.text
    gone_after = seconds_until_found(http, token, present=False)

    print(f"\nsearch: indexed after {appeared_after:.2f}s, removed after {gone_after:.2f}s")
    assert appeared_after < SEARCH_DEADLINE_SECONDS
    assert gone_after < SEARCH_DEADLINE_SECONDS
