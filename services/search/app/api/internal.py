"""Service-to-service endpoints.

Traefik routes only ``/api/search``, so ``/internal`` is reachable on the internal network only.
"""

from dataclasses import asdict

from fastapi import APIRouter, status

from app.core.deps import ReindexerDep
from app.schemas import ReindexJobResponse
from app.services.reindex import ReindexInProgressError, ReindexJob
from py_common.web.fastapi import ApiError

router = APIRouter(prefix="/internal/search", include_in_schema=False)


def _job(job: ReindexJob) -> ReindexJobResponse:
    return ReindexJobResponse.model_validate(asdict(job))


@router.post("/reindex", response_model=ReindexJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_reindex(reindexer: ReindexerDep) -> ReindexJobResponse:
    """Start rebuilding the index from the catalog; poll ``GET /reindex`` for the outcome.

    On success the alias moves to the new index and old versions are dropped.
    """
    try:
        job = await reindexer.start()
    except ReindexInProgressError as exc:
        raise ApiError("REINDEX_IN_PROGRESS", str(exc), status=409) from exc
    return _job(job)


@router.get("/reindex", response_model=ReindexJobResponse)
async def reindex_status(reindexer: ReindexerDep) -> ReindexJobResponse:
    """The last reindex: running, done (with its counts) or failed (with the reason)."""
    job = await reindexer.status()
    if job is None:
        raise ApiError("NOT_FOUND", "No reindex has run yet.", status=404)
    return _job(job)
