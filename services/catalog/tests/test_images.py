"""Presigned uploads, attaching images and the WebP rendition task (S3 mocked by moto)."""

import io
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from celery.exceptions import Retry
from PIL import Image
from rest_framework.test import APIClient

from contracts.enums import EventType
from contracts.events import ProductUpdated
from messaging.models import Outbox
from messaging.outbox import to_envelope
from products import storage, tasks
from products.images import SIZES, InvalidImageError, render_webp
from products.models import ImageStatus, ProductImage
from products.tasks import process_product_image, rendition_key
from sellers.models import Seller
from tests.conftest import BUCKET, image_bytes
from tests.factories import make_image, make_product, make_variant

pytestmark = pytest.mark.django_db

PRESIGN = "/api/catalog/seller/uploads/presign/"


def presign(client: APIClient, product_id: Any, **overrides: Any) -> Any:
    payload = {
        "product_id": str(product_id),
        "filename": "photo.jpg",
        "content_type": "image/jpeg",
        "size": 1024,
        **overrides,
    }
    return client.post(PRESIGN, payload, format="json")


# --- presign ----------------------------------------------------------------------------


def test_presign_returns_put_url_for_the_public_host(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)

    response = presign(seller_api, product.id, content_type="image/png", size=2048)

    assert response.status_code == 200
    body = response.json()
    url = urlparse(body["upload_url"])
    assert f"{url.scheme}://{url.netloc}" == "http://minio.localhost"
    assert url.path == f"/{BUCKET}/{body['key']}"
    assert body["key"].startswith(f"products/{product.id}/")
    assert body["key"].endswith(".png")
    assert body["method"] == "PUT"
    assert body["headers"] == {"Content-Type": "image/png"}
    assert body["expires_in"] == 600
    query = parse_qs(url.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    signed_headers = query["X-Amz-SignedHeaders"][0].split(";")
    assert {"host", "content-type", "content-length"} <= set(signed_headers)


def test_presign_keys_are_unique(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)

    first = presign(seller_api, product.id).json()["key"]
    second = presign(seller_api, product.id).json()["key"]

    assert first != second


@pytest.mark.parametrize("content_type", ["image/gif", "application/pdf", "text/html"])
def test_presign_rejects_other_content_types(
    seller_api: APIClient, seller: Seller, content_type: str
) -> None:
    response = presign(seller_api, make_product(seller=seller).id, content_type=content_type)

    assert response.status_code == 400
    assert "content_type" in response.json()["error"]["details"]


@pytest.mark.parametrize("size", [10 * 1024 * 1024 + 1, 0, -1])
def test_presign_rejects_bad_sizes(seller_api: APIClient, seller: Seller, size: int) -> None:
    response = presign(seller_api, make_product(seller=seller).id, size=size)

    assert response.status_code == 400
    assert "size" in response.json()["error"]["details"]


def test_presign_accepts_exactly_ten_megabytes(seller_api: APIClient, seller: Seller) -> None:
    response = presign(seller_api, make_product(seller=seller).id, size=10 * 1024 * 1024)

    assert response.status_code == 200


def test_presign_for_someone_elses_product_is_not_found(
    seller_api: APIClient, other_seller: Seller
) -> None:
    response = presign(seller_api, make_product(seller=other_seller).id)

    assert response.status_code == 404


# --- attach -----------------------------------------------------------------------------


def upload_original(s3: Any, product_id: Any, data: bytes, ext: str = "jpg") -> str:
    key = f"products/{product_id}/{uuid4()}.{ext}"
    s3.put_object(Bucket=BUCKET, Key=key, Body=data)
    return key


def test_attach_image_processes_it_after_commit(
    seller_api: APIClient, seller: Seller, s3: Any, django_capture_on_commit_callbacks: Any
) -> None:
    product = make_product(seller=seller)
    make_variant(product=product, stock=1)
    key = upload_original(s3, product.id, image_bytes((1600, 900)))

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = seller_api.post(
            f"/api/catalog/seller/products/{product.id}/images/", {"key": key}, format="json"
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == ImageStatus.PROCESSING
    assert body["original_key"] == key
    assert body["position"] == 0
    assert body["thumb_url"] is None
    assert len(callbacks) == 1  # the task is queued only once the row is committed

    callbacks[0]()

    image = ProductImage.objects.get(id=body["id"])
    assert image.status == ImageStatus.READY
    detail = seller_api.get(f"/api/catalog/seller/products/{product.id}/").json()
    assert detail["images"][0]["status"] == "ready"
    assert detail["image_url"].endswith("_medium.webp")


def test_attach_positions_follow_existing_images(
    seller_api: APIClient, seller: Seller, django_capture_on_commit_callbacks: Any
) -> None:
    product = make_product(seller=seller)
    make_image(product=product, position=4)

    with django_capture_on_commit_callbacks():
        response = seller_api.post(
            f"/api/catalog/seller/products/{product.id}/images/",
            {"key": f"products/{product.id}/{uuid4()}.webp"},
            format="json",
        )

    assert response.json()["position"] == 5


@pytest.mark.parametrize(
    "key",
    [
        "products/OTHER/abc.jpg",
        "PREFIX",
        "PREFIXnested/abc.jpg",
        "PREFIX../abc.jpg",
        "PREFIXabc.gif",
        "elsewhere/abc.jpg",
    ],
)
def test_attach_rejects_foreign_or_odd_keys(
    seller_api: APIClient, seller: Seller, key: str
) -> None:
    product = make_product(seller=seller)
    key = key.replace("PREFIX", f"products/{product.id}/").replace("OTHER", str(uuid4()))

    response = seller_api.post(
        f"/api/catalog/seller/products/{product.id}/images/", {"key": key}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IMAGE_KEY"
    assert not ProductImage.objects.exists()


def test_attach_same_upload_twice_conflicts(seller_api: APIClient, seller: Seller) -> None:
    product = make_product(seller=seller)
    existing = make_image(product=product)

    response = seller_api.post(
        f"/api/catalog/seller/products/{product.id}/images/",
        {"key": existing.original_key},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IMAGE_EXISTS"


# --- rendering --------------------------------------------------------------------------


def dimensions(data: bytes) -> tuple[str | None, tuple[int, int]]:
    with Image.open(io.BytesIO(data)) as image:
        return image.format, image.size


def test_render_webp_scales_by_longest_side() -> None:
    renditions = render_webp(image_bytes((2400, 1200)))

    assert {name: dimensions(data) for name, data in renditions.items()} == {
        "thumb": ("WEBP", (200, 100)),
        "medium": ("WEBP", (600, 300)),
        "large": ("WEBP", (1200, 600)),
    }


def test_render_webp_handles_portrait_images() -> None:
    renditions = render_webp(image_bytes((800, 1600), fmt="WEBP"))

    assert dimensions(renditions["large"])[1] == (600, 1200)
    assert dimensions(renditions["thumb"])[1] == (100, 200)


def test_render_webp_never_upscales() -> None:
    renditions = render_webp(image_bytes((150, 100), fmt="PNG"))

    assert {name: dimensions(data)[1] for name, data in renditions.items()} == dict.fromkeys(
        SIZES, (150, 100)
    )


def test_render_webp_keeps_transparency() -> None:
    renditions = render_webp(image_bytes((300, 300), fmt="PNG", mode="RGBA"))

    with Image.open(io.BytesIO(renditions["thumb"])) as image:
        assert image.mode == "RGBA"


@pytest.mark.parametrize(
    "data",
    [
        b"definitely not an image",
        b"%PDF-1.7 fake",
        image_bytes((10, 10), fmt="GIF", mode="P"),
        image_bytes((50, 50))[:200],  # truncated JPEG
    ],
)
def test_render_webp_rejects_non_images(data: bytes) -> None:
    with pytest.raises(InvalidImageError):
        render_webp(data)


def test_render_webp_rejects_huge_pixel_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("products.images.MAX_PIXELS", 100)

    with pytest.raises(InvalidImageError, match="too large"):
        render_webp(image_bytes((20, 20)))


# --- task ---------------------------------------------------------------------------------


@pytest.fixture
def processing_image(seller: Seller, s3: Any) -> Callable[..., ProductImage]:
    def build(data: bytes | None, ext: str = "jpg") -> ProductImage:
        product = make_product(seller=seller)
        key = f"products/{product.id}/{uuid4()}.{ext}"
        if data is not None:
            s3.put_object(Bucket=BUCKET, Key=key, Body=data)
        return make_image(
            product=product,
            original_key=key,
            status=ImageStatus.PROCESSING,
            thumb_key="",
            medium_key="",
            large_key="",
        )

    return build


def test_task_stores_three_webp_sizes_and_writes_outbox(
    processing_image: Callable[..., ProductImage], s3: Any
) -> None:
    image = processing_image(image_bytes((3000, 2000)))

    assert process_product_image(str(image.id)) == "ready"

    image.refresh_from_db()
    assert image.status == ImageStatus.READY
    expected = {
        "thumb": (200, 133),
        "medium": (600, 400),
        "large": (1200, 800),
    }
    for name, size in expected.items():
        key = getattr(image, f"{name}_key")
        assert key == rendition_key(image.original_key, name)
        stored = s3.get_object(Bucket=BUCKET, Key=key)
        assert stored["ContentType"] == "image/webp"
        assert dimensions(stored["Body"].read()) == ("WEBP", size)
    event = to_envelope(Outbox.objects.get())
    assert event.event_type is EventType.PRODUCT_UPDATED
    document = ProductUpdated.model_validate(event.payload)
    assert document.image_url == f"http://minio.localhost/{BUCKET}/{image.medium_key}"


def test_task_does_not_upscale_small_images(
    processing_image: Callable[..., ProductImage], s3: Any
) -> None:
    image = processing_image(image_bytes((120, 80), fmt="PNG"), ext="png")

    process_product_image(str(image.id))

    image.refresh_from_db()
    for key in (image.thumb_key, image.medium_key, image.large_key):
        data = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        assert dimensions(data) == ("WEBP", (120, 80))


def test_task_marks_non_images_failed(
    processing_image: Callable[..., ProductImage], s3: Any
) -> None:
    image = processing_image(b"<html>not an image</html>")

    assert process_product_image(str(image.id)) == "failed"

    image.refresh_from_db()
    assert image.status == ImageStatus.FAILED
    assert image.thumb_key == ""
    assert Outbox.objects.count() == 0
    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"products/{image.product_id}/")
    assert len(listing["Contents"]) == 1  # only the original


def test_task_marks_missing_uploads_failed(processing_image: Callable[..., ProductImage]) -> None:
    image = processing_image(None)

    assert process_product_image(str(image.id)) == "failed"

    image.refresh_from_db()
    assert image.status == ImageStatus.FAILED


def test_task_rejects_originals_over_the_limit(
    processing_image: Callable[..., ProductImage], settings: Any
) -> None:
    settings.IMAGE_MAX_UPLOAD_BYTES = 100
    image = processing_image(image_bytes((400, 400)))

    assert process_product_image(str(image.id)) == "failed"


def test_task_skips_unknown_and_finished_images(seller: Seller) -> None:
    done = make_image(product=make_product(seller=seller), status=ImageStatus.READY)

    assert process_product_image(str(uuid4())) == "skipped"
    assert process_product_image(str(done.id)) == "skipped"


def test_task_retries_storage_outages(
    processing_image: Callable[..., ProductImage], monkeypatch: pytest.MonkeyPatch
) -> None:
    image = processing_image(image_bytes((50, 50)))

    def unavailable(key: str, *, max_bytes: int) -> bytes:
        raise EndpointConnectionError(endpoint_url="http://minio:9000")

    monkeypatch.setattr(storage, "download", unavailable)

    with pytest.raises(Retry):
        process_product_image.apply(args=[str(image.id)], throw=True)
    image.refresh_from_db()
    assert image.status == ImageStatus.PROCESSING


def test_task_fails_the_image_when_retries_are_exhausted(
    processing_image: Callable[..., ProductImage], monkeypatch: pytest.MonkeyPatch
) -> None:
    image = processing_image(image_bytes((50, 50)))

    def unavailable(key: str, data: bytes, content_type: str) -> None:
        raise EndpointConnectionError(endpoint_url="http://minio:9000")

    monkeypatch.setattr(storage, "upload", unavailable)

    result = process_product_image.apply(
        args=[str(image.id)], retries=len(tasks.RETRY_DELAYS_SECONDS)
    )

    assert result.get() == "failed"
    image.refresh_from_db()
    assert image.status == ImageStatus.FAILED


def test_task_retries_other_storage_errors(
    processing_image: Callable[..., ProductImage], monkeypatch: pytest.MonkeyPatch
) -> None:
    image = processing_image(image_bytes((50, 50)))

    def denied(key: str, *, max_bytes: int) -> bytes:
        raise ClientError({"Error": {"Code": "SlowDown", "Message": "busy"}}, "GetObject")

    monkeypatch.setattr(storage, "download", denied)

    with pytest.raises(Retry):
        process_product_image.apply(args=[str(image.id)], throw=True)
