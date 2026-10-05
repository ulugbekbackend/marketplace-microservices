"""Full reindex: load every catalog product into a fresh index, then swap the alias.

Only one reindex runs at a time (a Redis lock shared by the API and the CLI). While it
runs, the new index sits behind ``<alias>_pending`` so product events reach it as well.
"""

import logging
import secrets
from dataclasses import dataclass
from typing import Any

from app.services.catalog import CatalogClient
from app.services.index import ProductIndex

logger = logging.getLogger(__name__)


class ReindexInProgressError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReindexResult:
    index: str
    indexed: int
    stale: int
    skipped: int
    removed_indices: list[str]


class Reindexer:
    def __init__(
        self,
        index: ProductIndex,
        catalog: CatalogClient,
        redis: Any,
        *,
        lock_seconds: int = 3600,
    ) -> None:
        self._index = index
        self._catalog = catalog
        self._redis = redis
        self._lock_seconds = lock_seconds

    @property
    def lock_key(self) -> str:
        return f"search:reindex:lock:{self._index.alias}"

    async def run(self) -> ReindexResult:
        token = secrets.token_hex(16)
        if not await self._redis.set(self.lock_key, token, nx=True, ex=self._lock_seconds):
            raise ReindexInProgressError("a reindex is already running")
        try:
            return await self._run()
        finally:
            if await self._redis.get(self.lock_key) == token:
                await self._redis.delete(self.lock_key)

    async def _run(self) -> ReindexResult:
        name = self._index.new_index_name()
        await self._index.create(name, aliases=[self._index.pending_alias], bulk=True)
        indexed = stale = skipped = 0
        try:
            async for page in self._catalog.pages():
                skipped += page.skipped
                stats = await self._index.bulk_load(name, page.products)
                indexed += stats.indexed
                stale += stats.stale
            await self._index.finish_bulk(name)
            removed = await self._index.swap(name)
        except BaseException:
            await self._index.drop(name)
            raise
        logger.info(
            "reindex finished",
            extra={"index": name, "indexed": indexed, "stale": stale, "skipped": skipped},
        )
        return ReindexResult(
            index=name, indexed=indexed, stale=stale, skipped=skipped, removed_indices=removed
        )
