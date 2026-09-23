"""URL slugs from titles in Uzbek (Latin or Cyrillic), Russian or English."""

from django.db import models
from django.utils.text import slugify
from unidecode import unidecode

FALLBACK_SLUG = "item"


def base_slug(text: str, *, max_length: int) -> str:
    """ASCII slug of ``text``; Uzbek Latin apostrophes and Cyrillic are transliterated."""
    slug = slugify(unidecode(text))[:max_length].strip("-")
    return slug or FALLBACK_SLUG


def unique_slug(
    model: type[models.Model],
    text: str,
    *,
    max_length: int,
    field: str = "slug",
) -> str:
    """A slug not used by any row of ``model`` yet: 'phone', 'phone-2', 'phone-3', ...

    The unique index stays the final guard against a concurrent insert.
    """
    # Leave room for a numeric suffix so the result always fits the column.
    base = base_slug(text, max_length=max_length - 8)
    taken = set(
        model._default_manager.filter(**{f"{field}__startswith": base}).values_list(
            field, flat=True
        )
    )
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"
