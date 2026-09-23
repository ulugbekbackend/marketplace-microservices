"""Slugs are ASCII for Uzbek Latin/Cyrillic and Russian titles and unique with suffixes."""

import pytest

from products.models import Product
from slugs import FALLBACK_SLUG, base_slug, unique_slug
from tests.factories import make_product


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Ўзбекистон қовуни", "uzbekiston-kovuni"),  # Uzbek Cyrillic
        ("Смартфон Samsung Galaxy", "smartfon-samsung-galaxy"),  # Russian
        ("Oʻzbekiston gʻalla", "ozbekiston-galla"),  # noqa: RUF001  Uzbek Latin okina
        ("Qo‘y go’shti", "qoy-goshti"),  # noqa: RUF001  typographic quotes
        ("iPhone 15 Pro", "iphone-15-pro"),
        ("!!!", FALLBACK_SLUG),
    ],
)
def test_base_slug_transliterates(title: str, slug: str) -> None:
    assert base_slug(title, max_length=100) == slug


def test_base_slug_respects_max_length() -> None:
    assert base_slug("a" * 50 + " b", max_length=10) == "a" * 10


@pytest.mark.django_db
def test_unique_slug_adds_numeric_suffixes() -> None:
    assert unique_slug(Product, "Телефон", max_length=220) == "telefon"
    make_product(slug="telefon")
    assert unique_slug(Product, "Телефон", max_length=220) == "telefon-2"
    make_product(slug="telefon-2")
    make_product(slug="telefon-3")
    assert unique_slug(Product, "Telefon", max_length=220) == "telefon-4"


@pytest.mark.django_db
def test_unique_slug_ignores_unrelated_prefix_matches() -> None:
    make_product(slug="telefonlar")
    assert unique_slug(Product, "Telefon", max_length=220) == "telefon"
