"""Request building and facet parsing without Elasticsearch."""

from typing import Any
from uuid import uuid4

from app.services.query import (
    PRICE_RANGES,
    SearchParams,
    Sort,
    build_search,
    build_suggest,
    facet_filters,
    parse_facets,
    text_query,
)


def test_empty_query_matches_everything() -> None:
    assert text_query("   ") == {"match_all": {}}


def test_non_facet_filters_go_into_the_query() -> None:
    seller = uuid4()

    body = build_search(SearchParams(seller=seller, in_stock=False), alias="products")

    assert body["query"]["bool"]["filter"] == [
        {"term": {"seller_id": str(seller)}},
        {"term": {"in_stock": False}},
    ]
    assert body["post_filter"] == {"bool": {"filter": []}}


def test_facet_filters_go_into_the_post_filter() -> None:
    category = uuid4()
    params = SearchParams(
        category=category, price_min=10, price_max=20, attributes={"color": ["red", "blue"]}
    )

    body = build_search(params, alias="products")

    post = body["post_filter"]["bool"]["filter"]
    assert {"term": {"category_ids": str(category)}} in post
    assert {"range": {"min_price": {"gte": 10, "lte": 20}}} in post
    assert len(post) == 3


def test_each_facet_skips_its_own_filter() -> None:
    params = SearchParams(category=uuid4(), price_min=1, attributes={"color": ["red"], "size": []})

    aggs = build_search(params, alias="products")["aggs"]
    filters = facet_filters(params)

    def used(agg: dict[str, Any]) -> list[Any]:
        clauses: list[Any] = agg["filter"]["bool"]["filter"]
        return clauses

    assert filters["category"] not in used(aggs["categories"])
    assert filters["price"] in used(aggs["categories"])
    assert filters["price"] not in used(aggs["price_ranges"])
    assert filters["attr:color"] in used(aggs["attributes"])
    assert filters["attr:color"] not in used(aggs["attr_0"])
    assert "attr_1" not in aggs  # "size" had no values


def test_paging_and_sorting() -> None:
    body = build_search(SearchParams(page=3, page_size=10, sort=Sort.PRICE_DESC), alias="p")

    assert (body["from_"], body["size"]) == (20, 10)
    assert body["sort"][0] == {"min_price": "desc"}
    assert body["index"] == "p"


def test_suggest_fetches_extra_hits_for_deduplication() -> None:
    body = build_suggest("tel", alias="products", limit=8)

    assert body["size"] == 16
    assert body["source"] == ["id", "slug", "title"]


def _aggs(category_sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "categories": {
            "ids": {
                "buckets": [
                    {
                        "key": "c2",
                        "doc_count": 3,
                        "sample": {"hits": {"hits": [{"_source": category_sample}]}},
                    },
                    {"key": "c9", "doc_count": 1, "sample": {"hits": {"hits": []}}},
                ]
            }
        },
        "price_ranges": {
            "ranges": {
                "buckets": [{"key": key, "doc_count": 0} for key, _low, _high in PRICE_RANGES]
            }
        },
        "attributes": {"nested": {"codes": {"buckets": []}}},
    }


def test_category_names_come_from_the_aligned_path() -> None:
    facets = parse_facets(
        _aggs({"category_ids": ["c1", "c2"], "category_path": ["Root", "Phones"]}),
        SearchParams(),
    )

    assert [(item.id, item.name, item.count) for item in facets.categories] == [
        ("c2", "Phones", 3),
        ("c9", "", 1),
    ]


def test_category_name_is_empty_when_the_path_is_short_or_unrelated() -> None:
    short = parse_facets(
        _aggs({"category_ids": ["c1", "c2"], "category_path": ["Root"]}), SearchParams()
    )
    unrelated = parse_facets(
        _aggs({"category_ids": ["c1"], "category_path": ["Root"]}), SearchParams()
    )

    assert short.categories[0].name == ""
    assert unrelated.categories[0].name == ""
