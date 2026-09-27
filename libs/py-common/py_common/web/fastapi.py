"""FastAPI wiring: health endpoints, Prometheus metrics, correlation id middleware,
the shared error shape and gateway identity dependencies.

    {"error": {"code": "OUT_OF_STOCK", "message": "...", "details": {...}}}
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from contracts.headers import X_CORRELATION_ID, X_REQUEST_ID
from py_common.auth import AuthError, CurrentUser, parse_user_headers
from py_common.context import request_context
from py_common.health import HealthRegistry

NextCall = Callable[[Request], Awaitable[Response]]


class ApiError(Exception):
    """A business error with a stable machine readable code.

    raise ApiError("OUT_OF_STOCK", "Not enough stock", status=409, details={...})
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


_STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "NOT_AUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "RATE_LIMITED",
}


async def _api_error_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, ApiError)
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
    return JSONResponse(
        error_body(exc.code, exc.message, exc.details), status_code=exc.status, headers=headers
    )


async def _validation_error_handler(request: Request, exc: Exception) -> Response:
    """Pydantic errors become ``{"field": ["message"]}``, the same details DRF gives."""
    assert isinstance(exc, RequestValidationError)
    details: dict[str, list[str]] = {}
    for error in exc.errors():
        # Drop the location prefix ("body", "query", "path") — clients know where they sent it.
        loc = [str(part) for part in error.get("loc", ())[1:]] or ["non_field_errors"]
        details.setdefault(".".join(loc), []).append(str(error.get("msg", "Invalid value.")))
    return JSONResponse(error_body("VALIDATION_ERROR", "Invalid input.", details), status_code=400)


async def _http_error_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODES.get(exc.status_code, "ERROR")
    return JSONResponse(
        error_body(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)


def optional_user(request: Request) -> CurrentUser | None:
    """Dependency: the gateway identity, or None for an anonymous request."""
    try:
        return parse_user_headers(request.headers)
    except AuthError as exc:
        raise ApiError("NOT_AUTHENTICATED", str(exc), status=401) from exc


def required_user(request: Request) -> CurrentUser:
    """Dependency: the gateway identity; anonymous requests get 401."""
    user = optional_user(request)
    if user is None:
        raise ApiError("NOT_AUTHENTICATED", "Authentication required.", status=401)
    return user


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
    """Attach the shared middleware, error handlers and health routes to a service."""
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(health_router(registry))
    app.include_router(health_router(registry, prefix=api_prefix))
