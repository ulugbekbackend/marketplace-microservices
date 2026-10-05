"""Pages through the catalog's search documents for a full reindex.

Contract (catalog, internal network only):
    GET /internal/catalog/search-documents/?page=&page_size=
        -> {"items": [ProductUpdated payload], "total", "page", "page_size"}
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from contracts.events import ProductUpdated

logger = logging.getLogger(__name__)

DOCUMENTS_PATH = "/internal/catalog/search-documents/"


class CatalogUnavailableError(RuntimeError):
    """The catalog did not answer, or answered something that is not a page."""


class _Page(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class DocumentPage:
    products: list[ProductUpdated]
    skipped: int


class CatalogClient:
    def __init__(self, http: httpx.AsyncClient, *, page_size: int = 200) -> None:
        self._http = http
        self._page_size = page_size

    async def _fetch(self, page: int) -> _Page:
        try:
            response = await self._http.get(
                DOCUMENTS_PATH, params={"page": page, "page_size": self._page_size}
            )
            response.raise_for_status()
            return _Page.model_validate_json(response.content)
        except (httpx.HTTPError, ValidationError) as exc:
            raise CatalogUnavailableError(f"catalog page {page}: {exc}") from exc

    async def pages(self) -> AsyncIterator[DocumentPage]:
        page = 1
        while True:
            data = await self._fetch(page)
            products: list[ProductUpdated] = []
            skipped = 0
            for raw in data.items:
                try:
                    products.append(ProductUpdated.model_validate(raw))
                except ValidationError as exc:
                    skipped += 1
                    logger.warning(
                        "invalid search document skipped",
                        extra={"product_id": raw.get("product_id"), "error": str(exc)},
                    )
            yield DocumentPage(products=products, skipped=skipped)
            if not data.items or page * data.page_size >= data.total:
                return
            page += 1
