"""Current price and stock from the catalog, with a short Redis cache.

Contract (catalog, internal network only):
    POST /internal/catalog/variants/bulk/  {"variant_ids": [...]}  ->  {"items": [VariantInfo]}
Unknown variants are left out of ``items``.
"""

import logging
from collections.abc import Iterable
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from py_common.web.fastapi import ApiError

logger = logging.getLogger(__name__)

BULK_PATH = "/internal/catalog/variants/bulk/"
CACHE_PREFIX = "cart:catalog:variant:"


class VariantAttribute(BaseModel):
    code: str
    name: str
    value: str


class VariantInfo(BaseModel):
    variant_id: UUID
    product_id: UUID
    product_slug: str
    title: str
    sku: str
    price_tiyin: int
    available: int
    is_active: bool
    seller_id: UUID
    shop_name: str
    image_url: str | None = None
    attributes: list[VariantAttribute] = []


class _BulkResponse(BaseModel):
    items: list[VariantInfo]


def catalog_unavailable() -> ApiError:
    return ApiError("CATALOG_UNAVAILABLE", "Catalog is temporarily unavailable.", status=503)


class CatalogClient:
    def __init__(self, http: httpx.AsyncClient, redis: Redis, *, cache_seconds: int):
        self._http = http
        self._redis = redis
        self._cache_seconds = cache_seconds

    async def variants(self, variant_ids: Iterable[UUID]) -> dict[UUID, VariantInfo]:
        wanted = sorted(set(variant_ids), key=str)
        if not wanted:
            return {}

        found: dict[UUID, VariantInfo] = {}
        cached = await self._redis.mget([f"{CACHE_PREFIX}{variant_id}" for variant_id in wanted])
        missing = []
        for variant_id, raw in zip(wanted, cached, strict=True):
            if raw is None:
                missing.append(variant_id)
            else:
                found[variant_id] = VariantInfo.model_validate_json(raw)

        if missing:
            fresh = await self._fetch(missing)
            if fresh:
                async with self._redis.pipeline(transaction=False) as pipe:
                    for info in fresh:
                        pipe.set(
                            f"{CACHE_PREFIX}{info.variant_id}",
                            info.model_dump_json(),
                            ex=self._cache_seconds,
                        )
                    await pipe.execute()
            found.update({info.variant_id: info for info in fresh})
        return found

    async def variant(self, variant_id: UUID) -> VariantInfo | None:
        return (await self.variants([variant_id])).get(variant_id)

    async def _fetch(self, variant_ids: list[UUID]) -> list[VariantInfo]:
        try:
            response = await self._http.post(
                BULK_PATH, json={"variant_ids": [str(variant_id) for variant_id in variant_ids]}
            )
            response.raise_for_status()
            return _BulkResponse.model_validate_json(response.content).items
        except (httpx.HTTPError, ValidationError) as exc:
            logger.warning("catalog bulk lookup failed", extra={"error": str(exc)})
            raise catalog_unavailable() from exc
