"""Shared fixtures. Tests run against real Postgres; S3 is mocked with moto."""

import io
import os
from collections.abc import Iterator
from typing import Any

# moto reads custom S3 endpoints when it is imported: register the MinIO-style hosts
# the settings below point at, so requests to them are served by the mock.
INTERNAL_ENDPOINT = "http://minio:9000"
PUBLIC_ENDPOINT = "http://minio.localhost"
os.environ.setdefault("MOTO_S3_CUSTOM_ENDPOINTS", f"{INTERNAL_ENDPOINT},{PUBLIC_ENDPOINT}")

import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402
from PIL import Image  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from config.celery import app as celery_app  # noqa: E402
from contracts.enums import UserRole  # noqa: E402
from products import storage  # noqa: E402
from products.models import Attribute, AttributeValue, Category  # noqa: E402
from sellers.models import Seller  # noqa: E402
from tests.factories import make_category, make_seller  # noqa: E402

BUCKET = "catalog-test"


@pytest.fixture(autouse=True)
def _eager_celery() -> Iterator[None]:
    # The app reads Django settings with the CELERY_ namespace, and those prefixed keys
    # win over plain ones, so override them under the same names.
    celery_app.conf.update(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    assert celery_app.conf.task_always_eager
    yield


@pytest.fixture(autouse=True)
def _s3_settings(settings: Any) -> None:
    settings.S3_ENDPOINT = INTERNAL_ENDPOINT
    settings.S3_PUBLIC_ENDPOINT = PUBLIC_ENDPOINT
    settings.S3_ACCESS_KEY = "test-access"
    settings.S3_SECRET_KEY = "test-secret"
    settings.S3_BUCKET = BUCKET
    settings.S3_REGION = "us-east-1"
    storage._client.cache_clear()


@pytest.fixture
def s3() -> Iterator[Any]:
    """A mocked bucket; clients are rebuilt inside the mock."""
    with mock_aws():
        storage._client.cache_clear()
        client = storage.internal_client()
        client.create_bucket(Bucket=BUCKET)
        yield client
    storage._client.cache_clear()


def image_bytes(size: tuple[int, int], fmt: str = "JPEG", mode: str = "RGB") -> bytes:
    color: Any = (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def seller_headers(seller: Seller) -> dict[str, str]:
    return {
        "HTTP_X_USER_ID": str(seller.user_id),
        "HTTP_X_USER_ROLE": UserRole.SELLER.value,
        "HTTP_X_SELLER_ID": str(seller.id),
    }


@pytest.fixture
def seller(db: None) -> Seller:
    return make_seller(shop_name="Tashkent Tech", slug="tashkent-tech")


@pytest.fixture
def other_seller(db: None) -> Seller:
    return make_seller(shop_name="Samarkand Goods", slug="samarkand-goods")


@pytest.fixture
def seller_api(seller: Seller) -> APIClient:
    client = APIClient()
    client.credentials(**seller_headers(seller))
    return client


@pytest.fixture
def other_seller_api(other_seller: Seller) -> APIClient:
    client = APIClient()
    client.credentials(**seller_headers(other_seller))
    return client


@pytest.fixture
def categories(db: None) -> dict[str, Category]:
    """electronics > phones > smartphones, electronics > laptops, and an inactive branch."""
    electronics = make_category(name="Electronics", slug="electronics")
    phones = make_category(name="Phones", slug="phones", parent=electronics)
    smartphones = make_category(name="Smartphones", slug="smartphones", parent=phones)
    laptops = make_category(name="Laptops", slug="laptops", parent=electronics)
    hidden = make_category(name="Hidden", slug="hidden", parent=electronics, is_active=False)
    hidden_child = make_category(name="Hidden child", slug="hidden-child", parent=hidden)
    clothes = make_category(name="Clothes", slug="clothes")
    return {
        "electronics": electronics,
        "phones": phones,
        "smartphones": smartphones,
        "laptops": laptops,
        "hidden": hidden,
        "hidden_child": hidden_child,
        "clothes": clothes,
    }


@pytest.fixture
def attributes(db: None) -> dict[str, AttributeValue]:
    color = Attribute.objects.create(name="Color", code="color")
    memory = Attribute.objects.create(name="Memory", code="memory")
    return {
        "red": AttributeValue.objects.create(attribute=color, value="red"),
        "black": AttributeValue.objects.create(attribute=color, value="black"),
        "128": AttributeValue.objects.create(attribute=memory, value="128 GB"),
        "256": AttributeValue.objects.create(attribute=memory, value="256 GB"),
    }
