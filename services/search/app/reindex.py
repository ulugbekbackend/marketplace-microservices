"""Full reindex from the command line: ``python -m app.reindex`` (``make reindex``)."""

import asyncio
import json
import sys

import httpx
from redis.asyncio import Redis

from app.core.config import Settings, load_settings
from app.main import make_elasticsearch
from app.services.catalog import CatalogClient, CatalogUnavailableError
from app.services.index import ProductIndex
from app.services.reindex import Reindexer, ReindexInProgressError


async def run(settings: Settings) -> int:
    es = make_elasticsearch(settings)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    http = httpx.AsyncClient(base_url=settings.catalog_url, timeout=settings.catalog_timeout)
    try:
        index = ProductIndex(
            es,
            alias=settings.index_alias,
            shards=settings.index_shards,
            replicas=settings.index_replicas,
        )
        reindexer = Reindexer(
            index,
            CatalogClient(http, page_size=settings.reindex_page_size),
            redis,
            lock_seconds=settings.reindex_lock_seconds,
        )
        try:
            result = await reindexer.run()
        except (ReindexInProgressError, CatalogUnavailableError) as exc:
            print(f"reindex failed: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "index": result.index,
                    "indexed": result.indexed,
                    "stale": result.stale,
                    "skipped": result.skipped,
                    "removed_indices": result.removed_indices,
                }
            )
        )
        return 0
    finally:
        await http.aclose()
        await redis.aclose()
        await es.close()


def main() -> None:  # pragma: no cover - thin process entry point
    sys.exit(asyncio.run(run(load_settings())))


if __name__ == "__main__":  # pragma: no cover
    main()
