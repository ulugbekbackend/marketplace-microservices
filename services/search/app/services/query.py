"""Elasticsearch request bodies for search and suggest, and parsing of the facets.

Faceting follows the multi-select pattern: filters a shopper picks in a facet
(category, price, attribute values) go into ``post_filter``, and each facet is computed
with every selected filter *except its own*. So picking "red" still shows how many blue
items there are, while the other facets narrow down. Seller, stock and the text query
are not facets and restrict everything.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

FACET_CATEGORY_SIZE = 50
FACET_ATTRIBUTE_CODES = 30
FACET_ATTRIBUTE_VALUES = 50
SUGGEST_LIMIT = 8

#: Price facet buckets on the card price (``min_price``) in tiyin; ``to`` is exclusive.
PRICE_RANGES: tuple[tuple[str, int | None, int | None], ...] = (
    ("lt_100k", None, 10_000_000),
    ("100k_500k", 10_000_000, 50_000_000),
    ("500k_1m", 50_000_000, 100_000_000),
    ("1m_5m", 100_000_000, 500_000_000),
    ("gte_5m", 500_000_000, None),
)

TEXT_FIELDS = ["title^3", "category_path^2", "shop_name", "description"]
SOURCE_FIELDS = [
    "id",
    "slug",
    "title",
    "seller_id",
    "shop_name",
    "min_price",
    "max_price",
    "in_stock",
    "image_url",
    "rating",
]


class Sort(StrEnum):
    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NEWEST = "newest"


_SORTS: dict[Sort, list[Any]] = {
    Sort.RELEVANCE: ["_score", {"created_at": "desc"}, {"id": "asc"}],
    Sort.PRICE_ASC: [{"min_price": "asc"}, {"id": "asc"}],
    Sort.PRICE_DESC: [{"min_price": "desc"}, {"id": "asc"}],
    Sort.NEWEST: [{"created_at": "desc"}, {"id": "asc"}],
}


@dataclass(frozen=True, slots=True)
class SearchParams:
    q: str = ""
    category: UUID | None = None
    seller: UUID | None = None
    price_min: int | None = None
    price_max: int | None = None
    in_stock: bool | None = None
    attributes: Mapping[str, Sequence[str]] = field(default_factory=dict)
    sort: Sort = Sort.RELEVANCE
    page: int = 1
    page_size: int = 20


# --- clauses ------------------------------------------------------------------------------


def text_query(q: str) -> dict[str, Any]:
    text = q.strip()
    if not text:
        return {"match_all": {}}
    return {
        "bool": {
            "should": [
                # Every word somewhere in the document ("samsung telefon").
                {
                    "multi_match": {
                        "query": text,
                        "fields": TEXT_FIELDS,
                        "type": "cross_fields",
                        "operator": "and",
                    }
                },
                # Typos inside one field ("telfon").
                {
                    "multi_match": {
                        "query": text,
                        "fields": TEXT_FIELDS,
                        "fuzziness": "AUTO",
                        "prefix_length": 1,
                        "operator": "and",
                    }
                },
                # Unfinished last word ("telef").
                {"match": {"title.autocomplete": {"query": text, "operator": "and"}}},
                {"match_phrase": {"title": {"query": text, "boost": 2}}},
            ],
            "minimum_should_match": 1,
        }
    }


def attribute_clause(code: str, values: Sequence[str]) -> dict[str, Any]:
    """Any of the values (OR) of one attribute code."""
    return {
        "nested": {
            "path": "attributes",
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"attributes.code": code}},
                        {"terms": {"attributes.value.normalized": list(values)}},
                    ]
                }
            },
        }
    }


def _attr_key(code: str) -> str:
    return f"attr:{code}"


def facet_filters(params: SearchParams) -> dict[str, dict[str, Any]]:
    """Post filters keyed by the facet they belong to."""
    filters: dict[str, dict[str, Any]] = {}
    if params.category is not None:
        filters["category"] = {"term": {"category_ids": str(params.category)}}
    price: dict[str, int] = {}
    if params.price_min is not None:
        price["gte"] = params.price_min
    if params.price_max is not None:
        price["lte"] = params.price_max
    if price:
        filters["price"] = {"range": {"min_price": price}}
    for code, values in sorted(params.attributes.items()):
        if values:
            filters[_attr_key(code)] = attribute_clause(code, values)
    return filters


def _all_but(filters: Mapping[str, dict[str, Any]], skip: str | None) -> dict[str, Any]:
    return {"bool": {"filter": [clause for key, clause in filters.items() if key != skip]}}


def selected_codes(params: SearchParams) -> list[str]:
    return sorted(code for code, values in params.attributes.items() if values)


def build_search(params: SearchParams, *, alias: str) -> dict[str, Any]:
    """Keyword arguments for ``AsyncElasticsearch.search``."""
    base_filters: list[dict[str, Any]] = []
    if params.seller is not None:
        base_filters.append({"term": {"seller_id": str(params.seller)}})
    if params.in_stock is not None:
        base_filters.append({"term": {"in_stock": params.in_stock}})

    filters = facet_filters(params)
    aggs: dict[str, Any] = {
        "categories": {
            "filter": _all_but(filters, "category"),
            "aggs": {
                "ids": {
                    "terms": {"field": "category_ids", "size": FACET_CATEGORY_SIZE},
                    "aggs": {
                        "sample": {
                            "top_hits": {
                                "size": 1,
                                "_source": {"includes": ["category_ids", "category_path"]},
                            }
                        }
                    },
                }
            },
        },
        "price_ranges": {
            "filter": _all_but(filters, "price"),
            "aggs": {
                "ranges": {
                    "range": {
                        "field": "min_price",
                        "keyed": False,
                        "ranges": [
                            {
                                "key": key,
                                **({"from": low} if low is not None else {}),
                                **({"to": high} if high is not None else {}),
                            }
                            for key, low, high in PRICE_RANGES
                        ],
                    }
                }
            },
        },
        "attributes": {
            "filter": _all_but(filters, None),
            "aggs": {
                "nested": {
                    "nested": {"path": "attributes"},
                    "aggs": {
                        "codes": {
                            "terms": {"field": "attributes.code", "size": FACET_ATTRIBUTE_CODES},
                            "aggs": {
                                "values": {
                                    "terms": {
                                        "field": "attributes.value",
                                        "size": FACET_ATTRIBUTE_VALUES,
                                    },
                                    "aggs": {"products": {"reverse_nested": {}}},
                                }
                            },
                        }
                    },
                }
            },
        },
    }
    # A selected attribute's own values are counted without its own filter.
    for position, code in enumerate(selected_codes(params)):
        aggs[f"attr_{position}"] = {
            "filter": _all_but(filters, _attr_key(code)),
            "aggs": {
                "nested": {
                    "nested": {"path": "attributes"},
                    "aggs": {
                        "code": {
                            "filter": {"term": {"attributes.code": code}},
                            "aggs": {
                                "values": {
                                    "terms": {
                                        "field": "attributes.value",
                                        "size": FACET_ATTRIBUTE_VALUES,
                                    },
                                    "aggs": {"products": {"reverse_nested": {}}},
                                }
                            },
                        }
                    },
                }
            },
        }

    return {
        "index": alias,
        "query": {"bool": {"must": [text_query(params.q)], "filter": base_filters}},
        "post_filter": _all_but(filters, None),
        "aggs": aggs,
        "sort": _SORTS[params.sort],
        "from_": (params.page - 1) * params.page_size,
        "size": params.page_size,
        "track_total_hits": True,
        "source": SOURCE_FIELDS,
    }


def build_suggest(q: str, *, alias: str, limit: int = SUGGEST_LIMIT) -> dict[str, Any]:
    return {
        "index": alias,
        "query": {
            "bool": {
                "must": [{"match": {"title.autocomplete": {"query": q, "operator": "and"}}}],
                "should": [{"match": {"title": {"query": q, "boost": 2}}}],
            }
        },
        "sort": ["_score", {"rating": "desc"}, {"id": "asc"}],
        # Extra hits so duplicate titles can be dropped and still fill the list.
        "size": limit * 2,
        "source": ["id", "slug", "title"],
        "track_total_hits": False,
    }


# --- facet parsing ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CategoryCount:
    id: str
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class PriceRangeCount:
    key: str
    from_tiyin: int | None
    to_tiyin: int | None
    count: int


@dataclass(frozen=True, slots=True)
class ValueCount:
    value: str
    count: int
    selected: bool


@dataclass(frozen=True, slots=True)
class AttributeCounts:
    code: str
    values: list[ValueCount]


@dataclass(frozen=True, slots=True)
class Facets:
    categories: list[CategoryCount]
    price_ranges: list[PriceRangeCount]
    attributes: list[AttributeCounts]


def _category_name(category_id: str, sample: Mapping[str, Any]) -> str:
    ids: list[str] = sample.get("category_ids", [])
    path: list[str] = sample.get("category_path", [])
    try:
        position = ids.index(category_id)
    except ValueError:
        return ""
    return path[position] if position < len(path) else ""


def parse_facets(aggs: Mapping[str, Any], params: SearchParams) -> Facets:
    categories = []
    for bucket in aggs["categories"]["ids"]["buckets"]:
        hits = bucket["sample"]["hits"]["hits"]
        sample = hits[0]["_source"] if hits else {}
        categories.append(
            CategoryCount(
                id=bucket["key"],
                name=_category_name(bucket["key"], sample),
                count=bucket["doc_count"],
            )
        )

    bounds = {key: (low, high) for key, low, high in PRICE_RANGES}
    price_ranges = [
        PriceRangeCount(
            key=bucket["key"],
            from_tiyin=bounds[bucket["key"]][0],
            to_tiyin=bounds[bucket["key"]][1],
            count=bucket["doc_count"],
        )
        for bucket in aggs["price_ranges"]["ranges"]["buckets"]
    ]

    selected = {code: set(values) for code, values in params.attributes.items() if values}
    values_by_code: dict[str, list[dict[str, Any]]] = {
        bucket["key"]: bucket["values"]["buckets"]
        for bucket in aggs["attributes"]["nested"]["codes"]["buckets"]
    }
    for position, code in enumerate(selected_codes(params)):
        values_by_code[code] = aggs[f"attr_{position}"]["nested"]["code"]["values"]["buckets"]

    attributes = []
    for code in sorted(values_by_code):
        chosen = {value.casefold() for value in selected.get(code, set())}
        values = [
            ValueCount(
                value=bucket["key"],
                count=bucket["products"]["doc_count"],
                selected=bucket["key"].casefold() in chosen,
            )
            for bucket in values_by_code[code]
        ]
        if values:
            attributes.append(AttributeCounts(code=code, values=values))
    return Facets(categories=categories, price_ranges=price_ranges, attributes=attributes)
