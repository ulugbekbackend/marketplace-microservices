"""The demo catalog seed builds the expected catalog and is safe to run twice."""

from typing import Any

import pytest
from django.core.management import call_command

from messaging.models import Outbox
from products.models import Category, Product, ProductImage, ProductVariant
from py_common.demo import SELLERS
from sellers.models import Seller

pytestmark = pytest.mark.django_db(transaction=True)


def test_seed_builds_the_demo_catalog(s3: Any) -> None:
    call_command("seed_catalog")

    assert Seller.objects.count() == len(SELLERS)
    assert {seller.id for seller in Seller.objects.all()} == {s.user_id for s in SELLERS}
    assert 25 <= Category.objects.count() <= 40
    assert Category.objects.filter(level=2).exists()  # three levels deep

    assert Product.objects.count() == 150
    assert Product.objects.filter(status="active").count() == 150
    assert 350 <= ProductVariant.objects.count() <= 500
    assert ProductVariant.objects.filter(price_tiyin__lte=0).count() == 0

    # Celery runs eagerly in tests, so every placeholder is already rendered.
    assert ProductImage.objects.count() == 150
    assert ProductImage.objects.filter(status="ready").count() == 150
    assert Outbox.objects.filter(event_type="product.updated").exists()


def test_seed_is_idempotent(s3: Any) -> None:
    call_command("seed_catalog", "--no-images")
    counts = (Seller.objects.count(), Category.objects.count(), Product.objects.count())
    variants = ProductVariant.objects.count()

    call_command("seed_catalog", "--no-images")

    assert (Seller.objects.count(), Category.objects.count(), Product.objects.count()) == counts
    assert ProductVariant.objects.count() == variants
