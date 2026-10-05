"""Public search endpoints (``/api/search`` is routed by Traefik)."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.core.deps import Search
from app.schemas import (
    AttributeFacet,
    AttributeValueFacet,
    CategoryFacet,
    Facets,
    PriceRangeFacet,
    SearchItem,
    SearchResponse,
    Suggestion,
    SuggestResponse,
)
from app.services.query import Facets as FacetCounts
from app.services.query import SearchParams, Sort
from py_common.web.fastapi import ApiError

router = APIRouter(prefix="/api/search", tags=["search"])

MAX_PAGE_SIZE = 100
#: Elasticsearch's default ``index.max_result_window``.
MAX_RESULT_WINDOW = 10_000
MAX_ATTRIBUTE_CODES = 20
MAX_ATTRIBUTE_VALUES = 50
MAX_VALUE_LENGTH = 200
_ATTR_KEY = re.compile(r"^attr\[([A-Za-z0-9_\-]{1,64})\]$")

_ATTR_PARAMETER = {
    "name": "attr",
    "in": "query",
    "required": False,
    "style": "deepObject",
    "explode": True,
    "description": (
        "Attribute filters: `attr[color]=red&attr[color]=blue&attr[size]=M`. "
        "Values of one code are OR-ed, different codes are AND-ed."
    ),
    "schema": {"type": "object", "additionalProperties": {"type": "string"}},
}


def _validation_error(field: str, message: str) -> ApiError:
    return ApiError("VALIDATION_ERROR", "Invalid input.", details={field: [message]})


def parse_attribute_filters(request: Request) -> dict[str, list[str]]:
    attributes: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        if not key.startswith("attr"):
            continue
        match = _ATTR_KEY.match(key)
        if match is None:
            raise _validation_error(key, "Use attr[<code>]=<value>.")
        value = value.strip()
        if not value:
            continue
        if len(value) > MAX_VALUE_LENGTH:
            raise _validation_error(key, f"At most {MAX_VALUE_LENGTH} characters.")
        values = attributes.setdefault(match.group(1), [])
        if value not in values:
            values.append(value)
        if len(values) > MAX_ATTRIBUTE_VALUES:
            raise _validation_error(key, f"At most {MAX_ATTRIBUTE_VALUES} values.")
    if len(attributes) > MAX_ATTRIBUTE_CODES:
        raise _validation_error("attr", f"At most {MAX_ATTRIBUTE_CODES} attributes.")
    return attributes


def _facets_out(facets: FacetCounts) -> Facets:
    return Facets(
        categories=[
            CategoryFacet(id=UUID(item.id), name=item.name, count=item.count)
            for item in facets.categories
        ],
        price_ranges=[
            PriceRangeFacet(
                key=item.key, from_tiyin=item.from_tiyin, to_tiyin=item.to_tiyin, count=item.count
            )
            for item in facets.price_ranges
        ],
        attributes=[
            AttributeFacet(
                code=item.code,
                values=[
                    AttributeValueFacet(
                        value=value.value, count=value.count, selected=value.selected
                    )
                    for value in item.values
                ],
            )
            for item in facets.attributes
        ],
    )


@router.get(
    "",
    response_model=SearchResponse,
    openapi_extra={"parameters": [_ATTR_PARAMETER]},
)
async def search(
    request: Request,
    service: Search,
    q: Annotated[str, Query(max_length=200)] = "",
    category: Annotated[UUID | None, Query(description="Category or any ancestor.")] = None,
    seller: Annotated[UUID | None, Query()] = None,
    price_min: Annotated[int | None, Query(ge=0, description="Tiyin, inclusive.")] = None,
    price_max: Annotated[int | None, Query(ge=0, description="Tiyin, inclusive.")] = None,
    in_stock: Annotated[bool | None, Query()] = None,
    sort: Annotated[Sort, Query()] = Sort.RELEVANCE,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> SearchResponse:
    """Full-text product search with filters, sorting and multi-select facets.

    Latin and Cyrillic spellings match each other ("telefon" = "телефон"), and every
    apostrophe variant of o' / g' is accepted. Price filters and facets use the card
    price (the lowest variant price).
    """
    if price_min is not None and price_max is not None and price_min > price_max:
        raise _validation_error("price_min", "Must not exceed price_max.")
    if page * page_size > MAX_RESULT_WINDOW:
        raise _validation_error("page", f"Only the first {MAX_RESULT_WINDOW} results are paged.")
    params = SearchParams(
        q=q,
        category=category,
        seller=seller,
        price_min=price_min,
        price_max=price_max,
        in_stock=in_stock,
        attributes=parse_attribute_filters(request),
        sort=sort,
        page=page,
        page_size=page_size,
    )
    result = await service.search(params)
    return SearchResponse(
        items=[SearchItem.model_validate(item) for item in result.items],
        total=result.total,
        page=page,
        page_size=page_size,
        facets=_facets_out(result.facets),
    )


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    service: Search, q: Annotated[str, Query(max_length=100)] = ""
) -> SuggestResponse:
    """Up to 8 title suggestions for a search box (prefix match, any script)."""
    items = await service.suggest(q)
    return SuggestResponse(items=[Suggestion.model_validate(item) for item in items])
