# ruff: noqa: RUF001, RUF002 - the Cyrillic and apostrophe look-alikes are the point here
"""Index settings and mappings of the product index.

Uzbek is written in both Latin and Cyrillic, and the Latin letters o' and g' come with
many apostrophe look-alikes (' ʻ ʼ ‘ ’ ` ´). Both index and query text go through the
same char filters, so every spelling ends up as one plain ASCII token:

1. ``uz_apostrophes`` drops apostrophe variants and the Cyrillic hard/soft signs
   (ъ is the Cyrillic spelling of the Uzbek tutuq belgisi: маъно = ma'no).
2. ``uz_cyrillic`` maps Cyrillic letters to the official Uzbek Latin alphabet
   (ш -> sh, ч -> ch, ў -> o, ғ -> g, қ -> q, ҳ -> h, х -> x ...).
3. ``lowercase`` + ``asciifolding`` handle case and accented Latin letters.

So "телефон" == "telefon" and "o'yinchoq" == "oʻyinchoq" == "ўйинчоқ" == "oyinchoq".
"""

from typing import Any

#: Characters removed before tokenizing: apostrophe look-alikes and Cyrillic ъ / ь.
APOSTROPHES = (
    "'"  # apostrophe
    "`"  # grave accent
    "´"  # acute accent
    "ʹ"  # modifier letter prime
    "ʻ"  # modifier letter turned comma: the official Uzbek o/g sign
    "ʼ"  # modifier letter apostrophe
    "ʽ"  # modifier letter reversed comma
    "‘"  # left single quotation mark
    "’"  # right single quotation mark
    "‛"  # single high-reversed-9 quotation mark
    "′"  # prime
)
_SIGNS = "ъЪьЬ"

#: Cyrillic (Uzbek and Russian) to Uzbek Latin. Upper case is generated below.
CYRILLIC_TO_LATIN: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sh",
    "ы": "i",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ў": "o",
    "қ": "q",
    "ғ": "g",
    "ҳ": "h",
}

AUTOCOMPLETE_MIN_GRAM = 2
AUTOCOMPLETE_MAX_GRAM = 20


def _cyrillic_mappings() -> list[str]:
    rules: list[str] = []
    for cyrillic, latin in CYRILLIC_TO_LATIN.items():
        rules.append(f"{cyrillic}=>{latin}")
        rules.append(f"{cyrillic.upper()}=>{latin}")
    return rules


def _apostrophe_pattern() -> str:
    escaped = "".join("\\" + char if char in "\\]^-[" else char for char in APOSTROPHES + _SIGNS)
    return f"[{escaped}]"


_CHAR_FILTERS = ["uz_apostrophes", "uz_cyrillic"]
_TOKEN_FILTERS = ["lowercase", "asciifolding"]


def index_settings(*, shards: int, replicas: int) -> dict[str, Any]:
    return {
        "number_of_shards": shards,
        "number_of_replicas": replicas,
        "max_ngram_diff": AUTOCOMPLETE_MAX_GRAM,
        "analysis": {
            "char_filter": {
                "uz_apostrophes": {
                    "type": "pattern_replace",
                    "pattern": _apostrophe_pattern(),
                    "replacement": "",
                },
                "uz_cyrillic": {"type": "mapping", "mappings": _cyrillic_mappings()},
            },
            "filter": {
                "autocomplete_edge": {
                    "type": "edge_ngram",
                    "min_gram": AUTOCOMPLETE_MIN_GRAM,
                    "max_gram": AUTOCOMPLETE_MAX_GRAM,
                }
            },
            "normalizer": {
                "uz_keyword": {
                    "type": "custom",
                    "char_filter": _CHAR_FILTERS,
                    "filter": _TOKEN_FILTERS,
                }
            },
            "analyzer": {
                "uz_text": {
                    "type": "custom",
                    "char_filter": _CHAR_FILTERS,
                    "tokenizer": "standard",
                    "filter": _TOKEN_FILTERS,
                },
                "uz_autocomplete": {
                    "type": "custom",
                    "char_filter": _CHAR_FILTERS,
                    "tokenizer": "standard",
                    "filter": [*_TOKEN_FILTERS, "autocomplete_edge"],
                },
            },
        },
    }


def _text(**extra: Any) -> dict[str, Any]:
    return {"type": "text", "analyzer": "uz_text", **extra}


INDEX_MAPPINGS: dict[str, Any] = {
    "dynamic": "strict",
    "properties": {
        "id": {"type": "keyword"},
        "title": _text(
            fields={
                "autocomplete": {
                    "type": "text",
                    "analyzer": "uz_autocomplete",
                    "search_analyzer": "uz_text",
                },
            }
        ),
        "description": _text(),
        "category_ids": {"type": "keyword"},
        "category_path": _text(fields={"raw": {"type": "keyword"}}),
        "seller_id": {"type": "keyword"},
        "shop_name": _text(fields={"raw": {"type": "keyword"}}),
        "slug": {"type": "keyword"},
        "min_price": {"type": "long"},
        "max_price": {"type": "long"},
        "in_stock": {"type": "boolean"},
        "attributes": {
            "type": "nested",
            "properties": {
                "code": {"type": "keyword"},
                "value": {
                    "type": "keyword",
                    "fields": {"normalized": {"type": "keyword", "normalizer": "uz_keyword"}},
                },
            },
        },
        "rating": {"type": "float"},
        "image_url": {"type": "keyword", "index": False},
        "created_at": {"type": "date"},
        "updated_at": {"type": "date"},
    },
}
