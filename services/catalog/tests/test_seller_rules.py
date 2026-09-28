"""Seller panel rules: stock totals, deleting images, and when a product may be active."""

import logging
import threading
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from contracts.enums import EventType, ProductStatus
from contracts.events import ProductUpdated
from messaging.models import Outbox
from messaging.outbox import to_envelope
from products import services, storage, tasks
from products.models import Category, ImageStatus, Product, ProductImage, ProductVariant
from products.tasks import process_product_image, rendition_key
from py_common.web.drf import ApiError
from sellers.models import Seller
from tests.conftest import BUCKET, image_bytes
from tests.factories import make_image, make_product, make_variant

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/catalog/seller/products/"
DRAFT = ProductStatus.DRAFT.value
ACTIVE = ProductStatus.ACTIVE.value


def product_url(product_id: Any) -> str:
    return f"{PRODUCTS}{product_id}/"


def image_url(product_id: Any, image_id: Any) -> str:
    return f"{PRODUCTS}{product_id}/images/{image_id}/"


def variant_url(variant_id: Any) -> str:
    return f"/api/catalog/seller/variants/{variant_id}/"


# --- stock totals -------------------------------------------------------------------------


def test_list_sums_stock_and_reserved_over_active_variants(
    seller_api: APIClient, seller: Seller
) -> None:
    product = make_product(seller=seller)
    make_variant(product=product, stock=10, reserved=3)
    make_variant(product=product, stock=5, reserved=1)
    make_variant(product=product, stock=100, reserved=50, is_active=False)
    make_image(product=product, position=0)
    make_image(product=product, position=1)  # a second image must not double the sums

    item = seller_api.get(PRODUCTS).json()["items"][0]

    assert (item["stock_total"], item["reserved_total"]) == (15, 4)
    assert item["variants_count"] == 3


def test_totals_are_zero_without_active_variants(seller_api: APIClient, seller: Seller) -> None:
    empty = make_product(seller=seller, status=DRAFT)
    hidden = make_product(seller=seller, status=DRAFT)
    make_variant(product=hidden, stock=7, reserved=2, is_active=False)

    items = {item["id"]: item for item in seller_api.get(PRODUCTS).json()["items"]}

    for product in (empty, hidden):
        item = items[str(product.id)]
        assert (item["stock_total"], item["reserved_total"]) == (0, 0)


def test_detail_has_the_totals(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)
    make_variant(product=product, stock=4, reserved=4)
    make_variant(product=product, stock=6, reserved=0)

    body = seller_api.get(product_url(product.id)).json()

    assert (body["stock_total"], body["reserved_total"]) == (10, 4)


def test_totals_filter_by_sku_does_not_change_the_sums(
    seller_api: APIClient, seller: Seller
) -> None:
    product = make_product(seller=seller)
    make_variant(product=product, sku="FIND-ME", stock=2, reserved=1)
    make_variant(product=product, stock=3, reserved=0)

    item = seller_api.get(f"{PRODUCTS}?q=find-me").json()["items"][0]

    assert (item["stock_total"], item["reserved_total"]) == (5, 1)


def _full_product(seller: Seller) -> Product:
    product = make_product(seller=seller)
    make_variant(product=product, stock=3, reserved=1)
    make_variant(product=product, stock=2)
    make_image(product=product)
    return product


def test_list_query_count_does_not_grow_with_the_page(
    seller_api: APIClient, seller: Seller
) -> None:
    _full_product(seller)
    with CaptureQueriesContext(connection) as one:
        assert len(seller_api.get(PRODUCTS).json()["items"]) == 1

    for _ in range(5):
        _full_product(seller)
    with CaptureQueriesContext(connection) as six:
        assert len(seller_api.get(PRODUCTS).json()["items"]) == 6

    assert len(six) == len(one)


def test_schema_marks_totals_as_required_integers(api: APIClient) -> None:
    schema = api.get("/api/catalog/schema/?format=json").json()

    for name in ("SellerProduct", "SellerProductDetail"):
        component = schema["components"]["schemas"][name]
        for field in ("stock_total", "reserved_total"):
            assert component["properties"][field]["type"] == "integer"
            assert field in component["required"]
    path = schema["paths"]["/api/catalog/seller/products/{product_id}/images/{image_id}/"]
    assert path["delete"]["operationId"] == "seller_images_delete"
    assert "204" in path["delete"]["responses"]


# --- deleting images ----------------------------------------------------------------------


@pytest.fixture
def deleted_keys(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(services, "delete_objects", lambda keys: calls.append(list(keys)))
    return calls


def test_delete_image_removes_row_and_files_after_commit(
    seller_api: APIClient,
    seller: Seller,
    deleted_keys: list[list[str]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    product = make_product(seller=seller)
    make_variant(product=product)
    image = make_image(product=product)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = seller_api.delete(image_url(product.id, image.id))

    assert response.status_code == 204
    assert not ProductImage.objects.filter(id=image.id).exists()
    assert deleted_keys == []  # nothing leaves the bucket before the commit
    assert len(callbacks) == 1

    callbacks[0]()

    assert deleted_keys == [
        [image.original_key, image.thumb_key, image.medium_key, image.large_key]
    ]


def test_delete_processing_image_removes_only_the_original(
    seller_api: APIClient,
    seller: Seller,
    deleted_keys: list[list[str]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    product = make_product(seller=seller, status=DRAFT)
    image = make_image(
        product=product,
        status=ImageStatus.PROCESSING,
        thumb_key="",
        medium_key="",
        large_key="",
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = seller_api.delete(image_url(product.id, image.id))

    assert response.status_code == 204
    assert deleted_keys == [[image.original_key]]


def test_delete_image_really_deletes_the_objects(
    seller_api: APIClient, seller: Seller, s3: Any, django_capture_on_commit_callbacks: Any
) -> None:
    product = make_product(seller=seller)
    make_variant(product=product)
    doomed = make_image(product=product, position=0)
    kept = make_image(product=product, position=1)
    for image in (doomed, kept):
        for key in (image.original_key, image.thumb_key, image.medium_key, image.large_key):
            s3.put_object(Bucket=BUCKET, Key=key, Body=b"x")

    with django_capture_on_commit_callbacks(execute=True):
        response = seller_api.delete(image_url(product.id, doomed.id))

    assert response.status_code == 204
    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"products/{product.id}/")
    assert sorted(obj["Key"] for obj in listing["Contents"]) == sorted(
        [kept.original_key, kept.thumb_key, kept.medium_key, kept.large_key]
    )


def test_delete_image_renumbers_positions(
    seller_api: APIClient,
    seller: Seller,
    deleted_keys: list[list[str]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    product = make_product(seller=seller)
    make_variant(product=product)
    first = make_image(product=product, position=0)
    doomed = make_image(product=product, position=1)
    third = make_image(product=product, position=2)
    fourth = make_image(product=product, position=7)  # an older gap is closed as well

    with django_capture_on_commit_callbacks(execute=True):
        response = seller_api.delete(image_url(product.id, doomed.id))

    assert response.status_code == 204
    positions = list(ProductImage.objects.filter(product=product).values_list("id", "position"))
    assert positions == [(first.id, 0), (third.id, 1), (fourth.id, 2)]
    detail = seller_api.get(product_url(product.id)).json()
    assert [image["position"] for image in detail["images"]] == [0, 1, 2]


def test_delete_image_of_active_product_writes_product_updated(
    seller_api: APIClient,
    seller: Seller,
    deleted_keys: list[list[str]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    product = make_product(seller=seller)
    make_variant(product=product)
    cover = make_image(product=product, position=0)
    second = make_image(product=product, position=1)
    before = Product.objects.get(id=product.id).updated_at

    with django_capture_on_commit_callbacks(execute=True):
        seller_api.delete(image_url(product.id, cover.id))

    event = to_envelope(Outbox.objects.get())
    assert event.event_type is EventType.PRODUCT_UPDATED
    document = ProductUpdated.model_validate(event.payload)
    assert document.product_id == product.id
    assert document.image_url == f"http://minio.localhost/{BUCKET}/{second.medium_key}"
    assert Product.objects.get(id=product.id).updated_at > before


def test_delete_image_of_draft_keeps_it_out_of_search(
    seller_api: APIClient,
    seller: Seller,
    deleted_keys: list[list[str]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    product = make_product(seller=seller, status=DRAFT)
    image = make_image(product=product)

    with django_capture_on_commit_callbacks(execute=True):
        seller_api.delete(image_url(product.id, image.id))

    # Same rule as every other change: a product that is not active stays deleted in search.
    assert to_envelope(Outbox.objects.get()).event_type is EventType.PRODUCT_DELETED


def test_delete_foreign_or_unknown_image_is_not_found(
    seller_api: APIClient,
    seller: Seller,
    other_seller: Seller,
    deleted_keys: list[list[str]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    foreign = make_product(seller=other_seller)
    foreign_image = make_image(product=foreign)
    mine = make_product(seller=seller)
    other_mine = make_product(seller=seller)
    my_image = make_image(product=other_mine)

    with django_capture_on_commit_callbacks(execute=True):
        responses = [
            seller_api.delete(image_url(foreign.id, foreign_image.id)),
            seller_api.delete(image_url(mine.id, foreign_image.id)),
            seller_api.delete(image_url(mine.id, my_image.id)),  # image of another product
            seller_api.delete(image_url(mine.id, uuid4())),
            seller_api.delete(image_url(uuid4(), my_image.id)),
        ]

    assert [r.status_code for r in responses] == [404] * len(responses)
    assert all(r.json()["error"]["code"] == "NOT_FOUND" for r in responses)
    assert ProductImage.objects.filter(id__in=[foreign_image.id, my_image.id]).count() == 2
    assert Outbox.objects.count() == 0
    assert deleted_keys == []


def test_storage_failure_is_logged_not_raised(
    seller_api: APIClient,
    seller: Seller,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: Any,
) -> None:
    def broken(keys: list[str]) -> None:
        raise RuntimeError("minio is down")

    monkeypatch.setattr(services, "delete_objects", broken)
    product = make_product(seller=seller, status=DRAFT)
    image = make_image(product=product)

    with (
        caplog.at_level(logging.ERROR, logger="products.services"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = seller_api.delete(image_url(product.id, image.id))

    assert response.status_code == 204
    assert not ProductImage.objects.filter(id=image.id).exists()
    assert "image objects were not deleted" in caplog.text


class _FakeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def delete_objects(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def test_storage_delete_reports_refused_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient({"Errors": [{"Key": "products/x/a.jpg", "Code": "AccessDenied"}]})
    monkeypatch.setattr(storage, "internal_client", lambda: client)

    with pytest.raises(RuntimeError, match=r"products/x/a\.jpg"):
        storage.delete_objects(["products/x/a.jpg"])

    assert client.calls[0]["Delete"] == {"Objects": [{"Key": "products/x/a.jpg"}], "Quiet": True}
    assert client.calls[0]["Bucket"] == BUCKET


def test_storage_delete_of_nothing_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient({})
    monkeypatch.setattr(storage, "internal_client", lambda: client)

    storage.delete_objects([])

    assert client.calls == []


def test_image_deleted_while_processing_leaves_no_renditions(
    seller: Seller, s3: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = make_product(seller=seller, status=DRAFT)
    key = f"products/{product.id}/{uuid4()}.jpg"
    s3.put_object(Bucket=BUCKET, Key=key, Body=image_bytes((300, 200)))
    image = make_image(
        product=product,
        original_key=key,
        status=ImageStatus.PROCESSING,
        thumb_key="",
        medium_key="",
        large_key="",
    )
    real_complete: Callable[..., bool] = services.complete_image

    def seller_deletes_first(image_id: UUID, keys: services.RenditionKeys) -> bool:
        ProductImage.objects.filter(id=image_id).delete()
        return real_complete(image_id, keys)

    monkeypatch.setattr(tasks, "complete_image", seller_deletes_first)

    process_product_image(str(image.id))

    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"products/{product.id}/")
    assert [obj["Key"] for obj in listing["Contents"]] == [key]


def test_concurrent_run_keeps_renditions_of_an_existing_image(
    seller: Seller, s3: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = make_product(seller=seller, status=DRAFT)
    key = f"products/{product.id}/{uuid4()}.jpg"
    s3.put_object(Bucket=BUCKET, Key=key, Body=image_bytes((300, 200)))
    image = make_image(
        product=product,
        original_key=key,
        status=ImageStatus.PROCESSING,
        thumb_key="",
        medium_key="",
        large_key="",
    )
    # Another run of the same message finished first: its files are the ones in use.
    monkeypatch.setattr(tasks, "complete_image", lambda image_id, keys: False)

    process_product_image(str(image.id))

    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"products/{product.id}/")
    assert sorted(obj["Key"] for obj in listing["Contents"]) == sorted(
        [key, *(rendition_key(key, name) for name in ("thumb", "medium", "large"))]
    )


# --- active needs an active variant -------------------------------------------------------


def test_create_active_product_is_rejected(
    seller_api: APIClient, categories: dict[str, Category]
) -> None:
    response = seller_api.post(
        PRODUCTS,
        {"title": "Empty", "category_id": str(categories["phones"].id), "status": ACTIVE},
        format="json",
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "at least one active variant" in error["message"]
    assert error["details"]["status"] == [error["message"]]
    assert not Product.objects.exists()
    assert Outbox.objects.count() == 0


def test_create_draft_then_variant_then_activate(
    seller_api: APIClient, categories: dict[str, Category]
) -> None:
    created = seller_api.post(
        PRODUCTS, {"title": "Phone", "category_id": str(categories["phones"].id)}, format="json"
    )
    assert created.status_code == 201
    product_id = created.json()["id"]
    variant = seller_api.post(
        f"{product_url(product_id)}variants/",
        {"sku": "PHONE-1", "price_tiyin": 100, "stock": 3},
        format="json",
    )
    assert variant.status_code == 201

    activated = seller_api.patch(product_url(product_id), {"status": ACTIVE}, format="json")

    assert activated.status_code == 200
    assert activated.json()["status"] == ACTIVE
    assert activated.json()["stock_total"] == 3


def test_service_rejects_creating_an_active_product(
    seller: Seller, categories: dict[str, Category]
) -> None:
    with pytest.raises(ApiError) as caught:
        services.create_product(seller, title="X", category=categories["phones"], status=ACTIVE)

    assert caught.value.status_code == 400
    assert caught.value.details == {"status": [services.NEEDS_ACTIVE_VARIANT]}


@pytest.mark.parametrize("variants", [[], [False], [False, False]])
def test_activate_without_active_variant_is_rejected(
    seller_api: APIClient, seller: Seller, variants: list[bool]
) -> None:
    product = make_product(seller=seller, status=DRAFT, title="Before")
    for is_active in variants:
        make_variant(product=product, is_active=is_active)

    response = seller_api.patch(
        product_url(product.id), {"status": ACTIVE, "title": "After"}, format="json"
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "status" in error["details"]
    product.refresh_from_db()
    assert (product.status, product.title) == (DRAFT, "Before")  # nothing was applied
    assert Outbox.objects.count() == 0


def test_activate_with_one_active_variant(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller, status=DRAFT)
    make_variant(product=product, is_active=False)
    make_variant(product=product, is_active=True)

    response = seller_api.patch(product_url(product.id), {"status": ACTIVE}, format="json")

    assert response.status_code == 200
    assert to_envelope(Outbox.objects.get()).event_type is EventType.PRODUCT_UPDATED


def test_other_changes_do_not_need_variants(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller, status=DRAFT)

    renamed = seller_api.patch(product_url(product.id), {"title": "Renamed"}, format="json")
    archived = seller_api.patch(product_url(product.id), {"status": "archived"}, format="json")

    assert (renamed.status_code, archived.status_code) == (200, 200)


# --- the last active variant ----------------------------------------------------------------


def test_deactivating_last_active_variant_of_active_product_conflicts(
    seller_api: APIClient, seller: Seller
) -> None:
    product = make_product(seller=seller)
    variant = make_variant(product=product, sku="ONLY")
    make_variant(product=product, is_active=False)

    response = seller_api.patch(
        variant_url(variant.id), {"is_active": False, "sku": "RENAMED"}, format="json"
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "LAST_ACTIVE_VARIANT"
    assert error["details"] == {"variant_id": str(variant.id)}
    variant.refresh_from_db()
    assert (variant.is_active, variant.sku) == (True, "ONLY")
    assert Outbox.objects.count() == 0


@pytest.mark.parametrize("status", [DRAFT, ProductStatus.ARCHIVED.value])
def test_last_variant_of_inactive_product_can_be_deactivated(
    seller_api: APIClient, seller: Seller, status: str
) -> None:
    variant = make_variant(product=make_product(seller=seller, status=status))

    response = seller_api.patch(variant_url(variant.id), {"is_active": False}, format="json")

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_other_variant_changes_of_the_last_variant_are_allowed(
    seller_api: APIClient, seller: Seller
) -> None:
    product = make_product(seller=seller)
    variant = make_variant(product=product)
    hidden = make_variant(product=product, is_active=False)

    price = seller_api.patch(variant_url(variant.id), {"price_tiyin": 77}, format="json")
    stays_active = seller_api.patch(variant_url(variant.id), {"is_active": True}, format="json")
    stays_hidden = seller_api.patch(variant_url(hidden.id), {"is_active": False}, format="json")

    assert [r.status_code for r in (price, stays_active, stays_hidden)] == [200, 200, 200]


@pytest.mark.django_db(transaction=True)
def test_parallel_deactivations_keep_one_active_variant(seller: Seller) -> None:
    product = make_product(seller=seller)
    variants = [make_variant(product=product) for _ in range(2)]
    results: list[object] = [None, None]
    barrier = threading.Barrier(2)

    def run(index: int) -> None:
        try:
            barrier.wait()
            services.update_variant(seller, variants[index].id, is_active=False)
            results[index] = "ok"
        except ApiError as exc:
            results[index] = exc.error_code
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(str(result) for result in results) == ["LAST_ACTIVE_VARIANT", "ok"]
    assert ProductVariant.objects.filter(product=product, is_active=True).count() == 1
