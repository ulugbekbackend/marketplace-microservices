"""Database constraints guard stock and money even when application code is wrong."""

import pytest
from django.db import IntegrityError, connection, transaction

from products.models import Category, ProductVariant
from tests.factories import make_reservation, make_variant

pytestmark = pytest.mark.django_db


def test_reserved_above_stock_is_rejected() -> None:
    variant = make_variant(stock=5, reserved=5)

    with (
        pytest.raises(IntegrityError, match="variant_reserved_within_stock"),
        transaction.atomic(),
    ):
        ProductVariant.objects.filter(id=variant.id).update(reserved=6)


def test_negative_stock_is_rejected() -> None:
    variant = make_variant(stock=1, reserved=0)

    # stock = -1 breaks both "stock >= 0" and "reserved <= stock"; Postgres names one.
    with (
        pytest.raises(
            IntegrityError, match=r"variant_stock_non_negative|variant_reserved_within_stock"
        ),
        transaction.atomic(),
    ):
        ProductVariant.objects.filter(id=variant.id).update(stock=-1)


def test_negative_reserved_is_rejected() -> None:
    with (
        pytest.raises(IntegrityError, match="variant_reserved_non_negative"),
        transaction.atomic(),
    ):
        make_variant(stock=1, reserved=-1)


def test_price_must_be_positive() -> None:
    with pytest.raises(IntegrityError, match="variant_price_positive"), transaction.atomic():
        make_variant(price_tiyin=0)


def test_sku_is_unique() -> None:
    make_variant(sku="SAME")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_variant(sku="SAME")


def test_one_reservation_per_order_and_variant() -> None:
    reservation = make_reservation()

    with (
        pytest.raises(IntegrityError, match="reservation_order_variant_unique"),
        transaction.atomic(),
    ):
        make_reservation(order_id=reservation.order_id, variant=reservation.variant)


def test_available_is_stock_minus_reserved() -> None:
    assert make_variant(stock=7, reserved=3).available == 4


def test_category_tree_descendants(categories: dict[str, Category]) -> None:
    electronics = categories["electronics"]
    electronics.refresh_from_db()  # later inserts moved the tree bounds

    slugs = set(electronics.get_descendants(include_self=True).values_list("slug", flat=True))

    assert slugs == {"electronics", "phones", "smartphones", "laptops", "hidden", "hidden-child"}
    categories["smartphones"].refresh_from_db()
    assert [c.slug for c in categories["smartphones"].get_ancestors(include_self=True)] == [
        "electronics",
        "phones",
        "smartphones",
    ]


def test_variant_check_constraints_exist_in_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'products_productvariant'::regclass AND contype = 'c'"
        )
        names = {row[0] for row in cursor.fetchall()}

    assert {
        "variant_price_positive",
        "variant_stock_non_negative",
        "variant_reserved_non_negative",
        "variant_reserved_within_stock",
    } <= names
