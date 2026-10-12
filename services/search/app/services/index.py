"""The product index: versioned concrete indices behind one alias.

* ``<alias>_v1`` / ``<alias>_v<timestamp>`` are the concrete indices.
* ``<alias>`` points at the live one; searches read through it.
* ``<alias>_pending`` points at an index a running reindex is filling. Event writes go to
  both, so an update that arrives during a reindex is not lost by the alias swap.

Writes use external versioning (``version_type=external_gte``): the version of a document
is the time of the change in epoch milliseconds, so an older event arriving late is a
no-op instead of overwriting newer data.

A deleted product stays as a tombstone (``{"id", "deleted": true}`` at the version of the
delete) instead of being removed: Elasticsearch forgets the version of a removed document
after ``index.gc_deletes`` (60 s), and an older update arriving later would bring the
product back. Searches leave tombstones out (``query.NOT_DELETED``); a reindex carries
them over.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from elasticsearch import AsyncElasticsearch, BadRequestError, ConflictError

from app.services.analysis import INDEX_MAPPINGS, REFRESH_INTERVAL, index_settings
from contracts.events import ProductUpdated

logger = logging.getLogger(__name__)

VERSION_TYPE = "external_gte"


class IndexMissingError(RuntimeError):
    """No index is behind the alias yet; writing now would auto-create a wrong index."""


class BulkLoadError(RuntimeError):
    """Elasticsearch rejected documents of a bulk request for a reason other than age."""


def epoch_millis(moment: datetime) -> int:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp() * 1000)


def to_document(product: ProductUpdated) -> dict[str, Any]:
    """The indexed document of a ``product.updated`` payload."""
    return {
        "id": str(product.product_id),
        "title": product.title,
        "description": product.description,
        "category_ids": [str(category_id) for category_id in product.category_ids],
        "category_path": list(product.category_path),
        "seller_id": str(product.seller_id),
        "shop_name": product.shop_name,
        "slug": product.slug,
        "min_price": product.min_price_tiyin,
        "max_price": product.max_price_tiyin,
        "in_stock": product.in_stock,
        "attributes": [
            {"code": code, "value": value}
            for code, value in dict.fromkeys((attr.code, attr.value) for attr in product.attributes)
        ],
        "rating": product.rating,
        "image_url": product.image_url,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


@dataclass(slots=True)
class BulkStats:
    indexed: int = 0
    stale: int = 0


@dataclass(frozen=True, slots=True)
class WriteTargets:
    live: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    @property
    def all(self) -> list[str]:
        return [*self.live, *(name for name in self.pending if name not in self.live)]


class ProductIndex:
    def __init__(
        self, es: AsyncElasticsearch, *, alias: str, shards: int = 1, replicas: int = 0
    ) -> None:
        self.es = es
        self.alias = alias
        self.pending_alias = f"{alias}_pending"
        self._shards = shards
        self._replicas = replicas

    # --- names ----------------------------------------------------------------------------

    @property
    def pattern(self) -> str:
        return f"{self.alias}_v*"

    def first_index_name(self) -> str:
        return f"{self.alias}_v1"

    def new_index_name(self, now: datetime | None = None) -> str:
        moment = now or datetime.now(UTC)
        return f"{self.alias}_v{moment:%Y%m%d%H%M%S%f}"

    # --- lifecycle ------------------------------------------------------------------------

    async def create(self, name: str, *, aliases: Iterable[str] = (), bulk: bool = False) -> None:
        settings = index_settings(shards=self._shards, replicas=self._replicas)
        if bulk:
            settings["refresh_interval"] = "-1"
        await self.es.indices.create(index=name, settings=settings, mappings=INDEX_MAPPINGS)
        await self._attach(name, aliases)

    async def _attach(self, name: str, aliases: Iterable[str]) -> None:
        """Point aliases at ``name`` once it can serve: searches on an index whose primary
        shard has not started yet fail with 503."""
        await self.es.cluster.health(index=name, wait_for_status="yellow", timeout="30s")
        actions = [{"add": {"index": name, "alias": alias}} for alias in aliases]
        if actions:
            await self.es.indices.update_aliases(actions=actions)

    async def ensure(self) -> str:
        """Create ``<alias>_v1`` behind the alias when no index serves it yet, or bring the
        live index's mapping up to date."""
        targets = await self.targets()
        if targets.live:
            await self.upgrade_mapping(targets.all)
            return targets.live[0]
        name = self.first_index_name()
        if await self.es.indices.exists(index=name):
            name = self.new_index_name()
        try:
            await self.create(name, aliases=[self.alias])
        except BadRequestError as exc:
            if exc.error != "resource_already_exists_exception":
                raise
            # Another replica created it a moment ago; adding the alias twice is harmless.
            await self._attach(name, [self.alias])
            return name
        logger.info("search index created", extra={"index": name, "alias": self.alias})
        return name

    async def upgrade_mapping(self, indices: list[str]) -> None:
        """Add fields (and sub-fields) this version maps but an older index lacks.

        Documents written before get the new sub-fields only when they are written again,
        so a mapping change still wants a reindex; new writes work at once.
        """
        await self.es.indices.put_mapping(
            index=",".join(indices), properties=INDEX_MAPPINGS["properties"]
        )

    async def targets(self) -> WriteTargets:
        """Concrete indices behind the live and the pending alias."""
        response = await self.es.indices.get_alias(index=self.pattern)
        live: list[str] = []
        pending: list[str] = []
        for name, info in sorted(response.body.items()):
            aliases = info.get("aliases", {})
            if self.alias in aliases:
                live.append(name)
            if self.pending_alias in aliases:
                pending.append(name)
        return WriteTargets(live=live, pending=pending)

    async def all_indices(self) -> list[str]:
        response = await self.es.indices.get(index=self.pattern)
        return sorted(response.body)

    async def refresh(self) -> None:
        await self.es.indices.refresh(index=self.alias)

    # --- event writes ---------------------------------------------------------------------

    async def _write_targets(self) -> list[str]:
        targets = (await self.targets()).all
        if not targets:
            raise IndexMissingError(f"no index behind alias {self.alias!r}")
        return targets

    async def upsert(self, product: ProductUpdated, *, version: int) -> bool:
        """Index the product. Returns False when a newer version is already indexed."""
        document = to_document(product)
        written = False
        for target in await self._write_targets():
            try:
                await self.es.index(
                    index=target,
                    id=document["id"],
                    document=document,
                    version=version,
                    version_type=VERSION_TYPE,
                )
                written = True
            except ConflictError:
                logger.info(
                    "stale product update ignored",
                    extra={"product_id": document["id"], "index": target, "version": version},
                )
        return written

    async def delete(self, product_id: UUID, *, version: int) -> bool:
        """Replace the product with a tombstone. Returns False when a newer version is
        already indexed."""
        applied = False
        for target in await self._write_targets():
            try:
                await self.es.index(
                    index=target,
                    id=str(product_id),
                    document={"id": str(product_id), "deleted": True},
                    version=version,
                    version_type=VERSION_TYPE,
                )
                applied = True
            except ConflictError:
                logger.info(
                    "stale product delete ignored",
                    extra={"product_id": str(product_id), "index": target, "version": version},
                )
        return applied

    # --- bulk load (reindex) --------------------------------------------------------------

    async def bulk_load(self, index: str, products: Iterable[ProductUpdated]) -> BulkStats:
        operations: list[dict[str, Any]] = []
        for product in products:
            document = to_document(product)
            operations.append(
                {
                    "index": {
                        "_index": index,
                        "_id": document["id"],
                        "version": epoch_millis(product.updated_at),
                        "version_type": VERSION_TYPE,
                    }
                }
            )
            operations.append(document)
        stats = BulkStats()
        if not operations:
            return stats
        response = await self.es.bulk(operations=operations)
        failures: list[dict[str, Any]] = []
        for item in response.body["items"]:
            result = item["index"]
            if result.get("status", 500) < 300:
                stats.indexed += 1
            elif result.get("status") == 409:
                # An event already wrote a newer version during the reindex.
                stats.stale += 1
            else:
                failures.append(result)
        if failures:
            raise BulkLoadError(f"{len(failures)} documents rejected: {failures[0].get('error')}")
        return stats

    async def copy_tombstones(self, index: str) -> int:
        """Copy the live index's tombstones, with their versions, into ``index``.

        A product the catalog still listed when it was read but deleted meanwhile keeps its
        newer tombstone; one that came back after its delete keeps the newer document.
        """
        live = (await self.targets()).live
        if not live:
            return 0
        # _reindex reads through search: a delete of the last second must be visible.
        await self.es.indices.refresh(index=live[0])
        response = await self.es.reindex(
            source={"index": live[0], "query": {"term": {"deleted": True}}},
            dest={"index": index, "version_type": "external"},
            conflicts="proceed",
            wait_for_completion=True,
        )
        created: int = response.body.get("created", 0)
        return created

    async def finish_bulk(self, index: str) -> None:
        await self.es.indices.put_settings(
            index=index, settings={"refresh_interval": REFRESH_INTERVAL}
        )
        await self.es.indices.refresh(index=index)

    async def swap(self, new_index: str) -> list[str]:
        """Point the alias at ``new_index`` and drop every other version, atomically."""
        old = [name for name in await self.all_indices() if name != new_index]
        actions: list[dict[str, Any]] = [
            {"add": {"index": new_index, "alias": self.alias}},
            {"remove": {"index": new_index, "alias": self.pending_alias}},
            *({"remove_index": {"index": name}} for name in old),
        ]
        await self.es.indices.update_aliases(actions=actions)
        return old

    async def drop(self, index: str) -> None:
        await self.es.indices.delete(index=index, ignore_unavailable=True)
