"""Runs searches and suggestions against the product alias."""

import logging
import time
from dataclasses import dataclass
from typing import Any

from elasticsearch import ApiError as ESApiError
from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch import ConnectionError as ESConnectionError
from elasticsearch import TransportError as ESTransportError

from app.core.metrics import SEARCH_LATENCY
from app.services.query import (
    SUGGEST_LIMIT,
    Facets,
    SearchParams,
    build_search,
    build_suggest,
    parse_facets,
)
from py_common.web.fastapi import ApiError

logger = logging.getLogger(__name__)

SUGGEST_MIN_LENGTH = 2


def search_unavailable() -> ApiError:
    return ApiError("SEARCH_UNAVAILABLE", "Search is temporarily unavailable.", status=503)


@dataclass(frozen=True, slots=True)
class SearchResult:
    items: list[dict[str, Any]]
    total: int
    facets: Facets


class SearchService:
    def __init__(self, es: AsyncElasticsearch, *, alias: str) -> None:
        self._es = es
        self._alias = alias

    async def search(self, params: SearchParams) -> SearchResult:
        started = time.perf_counter()
        try:
            response = await self._es.search(**build_search(params, alias=self._alias))
        except NotFoundError:
            # The index is not created yet: nothing to find.
            return SearchResult(items=[], total=0, facets=Facets([], [], []))
        except (ESConnectionError, ESTransportError, ESApiError) as exc:
            logger.warning("search failed", extra={"error": str(exc)})
            raise search_unavailable() from exc
        finally:
            SEARCH_LATENCY.labels(endpoint="search").observe(time.perf_counter() - started)
        body = response.body
        return SearchResult(
            items=[hit["_source"] for hit in body["hits"]["hits"]],
            total=body["hits"]["total"]["value"],
            facets=parse_facets(body["aggregations"], params),
        )

    async def suggest(self, q: str, *, limit: int = SUGGEST_LIMIT) -> list[dict[str, Any]]:
        text = q.strip()
        if len(text) < SUGGEST_MIN_LENGTH:
            return []
        started = time.perf_counter()
        try:
            response = await self._es.search(**build_suggest(text, alias=self._alias, limit=limit))
        except NotFoundError:
            return []
        except (ESConnectionError, ESTransportError, ESApiError) as exc:
            logger.warning("suggest failed", extra={"error": str(exc)})
            raise search_unavailable() from exc
        finally:
            SEARCH_LATENCY.labels(endpoint="suggest").observe(time.perf_counter() - started)
        suggestions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in response.body["hits"]["hits"]:
            source = hit["_source"]
            key = source["title"].casefold()
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(source)
            if len(suggestions) == limit:
                break
        return suggestions
