"""Response bodies of the search API. Money is integer tiyin."""

from uuid import UUID

from pydantic import BaseModel, Field


class SearchItem(BaseModel):
    """What a product card needs."""

    id: UUID
    slug: str
    title: str
    seller_id: UUID
    shop_name: str
    min_price: int = Field(description="Lowest variant price, tiyin.")
    max_price: int = Field(description="Highest variant price, tiyin.")
    in_stock: bool
    image_url: str | None = None
    rating: float = 0.0


class CategoryFacet(BaseModel):
    id: UUID
    name: str
    count: int


class PriceRangeFacet(BaseModel):
    key: str
    from_tiyin: int | None = Field(description="Inclusive lower bound; null = open.")
    to_tiyin: int | None = Field(description="Exclusive upper bound; null = open.")
    count: int


class AttributeValueFacet(BaseModel):
    value: str
    count: int
    selected: bool


class AttributeFacet(BaseModel):
    code: str
    values: list[AttributeValueFacet]


class Facets(BaseModel):
    categories: list[CategoryFacet]
    price_ranges: list[PriceRangeFacet]
    attributes: list[AttributeFacet]


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    page: int
    page_size: int
    facets: Facets


class Suggestion(BaseModel):
    id: UUID
    slug: str
    title: str


class SuggestResponse(BaseModel):
    items: list[Suggestion]


class ReindexResponse(BaseModel):
    index: str
    indexed: int
    stale: int = Field(description="Documents an event had already replaced with a newer one.")
    skipped: int = Field(description="Catalog documents that failed validation.")
    removed_indices: list[str]
