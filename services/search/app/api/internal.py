"""Service-to-service endpoints.

Traefik routes only ``/api/search``, so ``/internal`` is reachable on the internal network only.
"""

from fastapi import APIRouter

from app.core.deps import ReindexerDep
from app.schemas import ReindexResponse
from app.services.catalog import CatalogUnavailableError
from app.services.reindex import ReindexInProgressError
from py_common.web.fastapi import ApiError

router = APIRouter(prefix="/internal/search", include_in_schema=False)


@router.post("/reindex", response_model=ReindexResponse)
async def reindex(reindexer: ReindexerDep) -> ReindexResponse:
    """Rebuild the index from the catalog and swap the alias; old versions are dropped."""
    try:
        result = await reindexer.run()
    except ReindexInProgressError as exc:
        raise ApiError("REINDEX_IN_PROGRESS", str(exc), status=409) from exc
    except CatalogUnavailableError as exc:
        raise ApiError(
            "CATALOG_UNAVAILABLE", "Catalog is temporarily unavailable.", status=502
        ) from exc
    return ReindexResponse(
        index=result.index,
        indexed=result.indexed,
        stale=result.stale,
        skipped=result.skipped,
        removed_indices=result.removed_indices,
    )
