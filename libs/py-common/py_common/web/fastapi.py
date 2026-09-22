"""FastAPI wiring: health endpoints, Prometheus metrics, correlation id middleware."""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from contracts.headers import X_CORRELATION_ID, X_REQUEST_ID
from py_common.context import request_context
from py_common.health import HealthRegistry

NextCall = Callable[[Request], Awaitable[Response]]


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Continue the correlation id the gateway sent, or start a new one."""

    async def dispatch(self, request: Request, call_next: NextCall) -> Response:
        raw = request.headers.get(X_CORRELATION_ID)
        correlation_id = _parse_uuid(raw)
        with request_context(
            correlation_id=correlation_id, request_id=request.headers.get(X_REQUEST_ID)
        ) as (current, request_id):
            response = await call_next(request)
            response.headers[X_CORRELATION_ID] = str(current)
            response.headers[X_REQUEST_ID] = request_id
            return response


def _parse_uuid(raw: str | None):  # type: ignore[no-untyped-def]
    from uuid import UUID

    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def health_router(registry: HealthRegistry, *, prefix: str = "") -> APIRouter:
    """Liveness, readiness and metrics, mounted at the root and under the API prefix."""
    router = APIRouter(prefix=prefix)

    @router.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health/ready", include_in_schema=False)
    async def ready(response: Response) -> dict[str, object]:
        report = await registry.run()
        if not report.ok:
            response.status_code = 503
        return report.as_dict()

    @router.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router


def setup(app: FastAPI, *, registry: HealthRegistry, api_prefix: str) -> None:
    """Attach the shared middleware and health routes to a service application."""
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health_router(registry))
    app.include_router(health_router(registry, prefix=api_prefix))
