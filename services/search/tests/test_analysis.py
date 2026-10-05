# ruff: noqa: RUF001 - Cyrillic and apostrophe variants are the test data
"""The Uzbek analyzer: one token for every spelling of a word."""

import re

import pytest
from app.services.analysis import APOSTROPHES, CYRILLIC_TO_LATIN, index_settings
from app.services.index import ProductIndex


def test_every_cyrillic_letter_is_mapped_in_both_cases() -> None:
    mappings = index_settings(shards=1, replicas=0)["analysis"]["char_filter"]["uz_cyrillic"][
        "mappings"
    ]

    assert len(mappings) == 2 * len(CYRILLIC_TO_LATIN)
    assert "Ш=>sh" in mappings
    assert "ў=>o" in mappings


def test_apostrophe_pattern_matches_every_variant() -> None:
    pattern = index_settings(shards=1, replicas=0)["analysis"]["char_filter"]["uz_apostrophes"][
        "pattern"
    ]

    for char in APOSTROPHES + "ъь":
        assert re.fullmatch(pattern, char), char
    assert re.fullmatch(pattern, "o") is None


async def analyze(index: ProductIndex, text: str, analyzer: str = "uz_text") -> list[str]:
    response = await index.es.indices.analyze(index=index.alias, analyzer=analyzer, text=text)
    return [token["token"] for token in response["tokens"]]


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("Телефон", ["telefon"]),
        ("telefon", ["telefon"]),
        ("O'yinchoq", ["oyinchoq"]),
        ("Oʻyinchoq", ["oyinchoq"]),
        ("o‘yinchoq", ["oyinchoq"]),
        ("oʼyinchoq", ["oyinchoq"]),
        ("o`yinchoq", ["oyinchoq"]),
        ("ўйинчоқ", ["oyinchoq"]),
        ("G'ISHT Ғишт", ["gisht", "gisht"]),
        ("ШАХМАТ", ["shaxmat"]),
        ("маъно ma'no", ["mano", "mano"]),
        ("Café", ["cafe"]),
        ("Ёмғир", ["yomgir"]),
    ],
)
async def test_spellings_become_one_token(
    index: ProductIndex, text: str, tokens: list[str]
) -> None:
    await index.ensure()

    assert await analyze(index, text) == tokens


async def test_autocomplete_indexes_prefixes(index: ProductIndex) -> None:
    await index.ensure()

    assert await analyze(index, "Тел", "uz_autocomplete") == ["te", "tel"]
