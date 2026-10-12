"""Full reindex: load every catalog product into a fresh index, then swap the alias.

Only one reindex runs at a time (a Redis lock shared by the API and the CLI). While it
runs, the new index sits behind ``<alias>_pending`` so product events reach it as well.

The API starts a reindex in the background (``start``) and reports it through ``status``:
the job lives in Redis, so any replica can answer. The CLI waits for it (``run``).
"""

import asyncio
import json
import logging
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.services.catalog import CatalogClient, CatalogUnavailableError
from app.services.index import ProductIndex

logger = logging.getLogger(__name__)

JobState = Literal["running", "done", "failed"]

#: How long the last job's report stays readable.
STATUS_TTL_SECONDS = 7 * 24 * 3600


class ReindexInProgressError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReindexResult:
    index: str
    indexed: int
    stale: int
    skipped: int
    tombstones: int
    removed_indices: list[str]


@dataclass(frozen=True, slots=True)
class ReindexJob:
    job_id: str
    status: JobState
    started_at: datetime
    finished_at: datetime | None = None
    result: ReindexResult | None = None
    error_code: str | None = None
    error: str | None = None

    def to_json(self) -> str:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: str) -> "ReindexJob":
        data: dict[str, Any] = json.loads(raw)
        result = data.pop("result")
        return cls(
            **{
                **data,
                "started_at": datetime.fromisoformat(data["started_at"]),
                "finished_at": (
                    datetime.fromisoformat(data["finished_at"]) if data["finished_at"] else None
                ),
            },
            result=ReindexResult(**result) if result else None,
        )


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
        self._task: asyncio.Task[ReindexJob] | None = None

    @property
    def lock_key(self) -> str:
        return f"search:reindex:lock:{self._index.alias}"

    @property
    def status_key(self) -> str:
        return f"search:reindex:status:{self._index.alias}"

    # --- background (API) -----------------------------------------------------------------

    async def start(self) -> ReindexJob:
        """Take the lock and start the reindex in the background."""
        token = await self._acquire()
        job = ReindexJob(job_id=token, status="running", started_at=datetime.now(UTC))
        await self._save(job)
        self._task = asyncio.create_task(self._finish(job, token), name="search-reindex")
        return job

    async def status(self) -> ReindexJob | None:
        """The last job. A running one whose lock is gone died with its process."""
        raw = await self._redis.get(self.status_key)
        if raw is None:
            return None
        job = ReindexJob.from_json(raw)
        if job.status == "running" and await self._redis.get(self.lock_key) != job.job_id:
            return ReindexJob(
                job_id=job.job_id,
                status="failed",
                started_at=job.started_at,
                error_code="REINDEX_INTERRUPTED",
                error="The reindex stopped before it finished.",
            )
        return job

    async def wait(self) -> ReindexJob | None:
        """Wait for the job this process started, if any."""
        if self._task is None:
            return None
        return await asyncio.shield(self._task)

    async def aclose(self) -> None:
        """Stop a running job on shutdown; its half built index is dropped."""
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _finish(self, job: ReindexJob, token: str) -> ReindexJob:
        try:
            result = await self._run()
        except CatalogUnavailableError as exc:
            done = self._failed(job, "CATALOG_UNAVAILABLE", "Catalog is temporarily unavailable.")
            logger.warning("reindex failed", extra={"error": str(exc)})
        except asyncio.CancelledError:
            done = self._failed(job, "REINDEX_INTERRUPTED", "The service stopped the reindex.")
            await self._save(done)
            await self._release(token)
            raise
        except Exception as exc:
            done = self._failed(job, "REINDEX_FAILED", str(exc))
            logger.exception("reindex failed")
        else:
            done = ReindexJob(
                job_id=job.job_id,
                status="done",
                started_at=job.started_at,
                finished_at=datetime.now(UTC),
                result=result,
            )
        await self._save(done)
        await self._release(token)
        return done

    @staticmethod
    def _failed(job: ReindexJob, code: str, message: str) -> ReindexJob:
        return ReindexJob(
            job_id=job.job_id,
            status="failed",
            started_at=job.started_at,
            finished_at=datetime.now(UTC),
            error_code=code,
            error=message,
        )

    # --- in the foreground (CLI) ----------------------------------------------------------

    async def run(self) -> ReindexResult:
        token = await self._acquire()
        try:
            return await self._run()
        finally:
            await self._release(token)

    # --- internals ------------------------------------------------------------------------

    async def _acquire(self) -> str:
        token = secrets.token_hex(16)
        if not await self._redis.set(self.lock_key, token, nx=True, ex=self._lock_seconds):
            raise ReindexInProgressError("a reindex is already running")
        return token

    async def _release(self, token: str) -> None:
        if await self._redis.get(self.lock_key) == token:
            await self._redis.delete(self.lock_key)

    async def _save(self, job: ReindexJob) -> None:
        await self._redis.set(self.status_key, job.to_json(), ex=STATUS_TTL_SECONDS)

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
            tombstones = await self._index.copy_tombstones(name)
            await self._index.finish_bulk(name)
            removed = await self._index.swap(name)
        except BaseException:
            await self._index.drop(name)
            raise
        logger.info(
            "reindex finished",
            extra={
                "index": name,
                "indexed": indexed,
                "stale": stale,
                "skipped": skipped,
                "tombstones": tombstones,
            },
        )
        return ReindexResult(
            index=name,
            indexed=indexed,
            stale=stale,
            skipped=skipped,
            tombstones=tombstones,
            removed_indices=removed,
        )
