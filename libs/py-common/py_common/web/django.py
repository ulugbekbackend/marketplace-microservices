"""Django wiring: health endpoints, Prometheus metrics, correlation id middleware."""

import json
from collections.abc import Callable
from uuid import UUID

from asgiref.sync import async_to_sync
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import path
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from contracts.headers import X_CORRELATION_ID, X_REQUEST_ID
from py_common.context import request_context
from py_common.health import HealthRegistry


def correlation_id_middleware(
    get_response: Callable[[HttpRequest], HttpResponse],
) -> Callable[[HttpRequest], HttpResponse]:
    """Bind the gateway's correlation id so every log line of this request carries it."""

    def middleware(request: HttpRequest) -> HttpResponse:
        raw = request.headers.get(X_CORRELATION_ID)
        try:
            correlation_id = UUID(raw) if raw else None
        except ValueError:
            correlation_id = None

        with request_context(
            correlation_id=correlation_id, request_id=request.headers.get(X_REQUEST_ID)
        ) as (current, request_id):
            response = get_response(request)
            response[X_CORRELATION_ID] = str(current)
            response[X_REQUEST_ID] = request_id
            return response

    return middleware


def health_urlpatterns(registry: HealthRegistry, *, prefix: str = "") -> list[object]:
    """URL patterns for /health/live, /health/ready and /metrics."""

    def live(request: HttpRequest) -> JsonResponse:
        return JsonResponse({"status": "ok"})

    def ready(request: HttpRequest) -> HttpResponse:
        report = async_to_sync(registry.run)()
        return HttpResponse(
            json.dumps(report.as_dict()),
            content_type="application/json",
            status=200 if report.ok else 503,
        )

    def metrics(request: HttpRequest) -> HttpResponse:
        return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)

    return [
        path(f"{prefix}health/live", live),
        path(f"{prefix}health/ready", ready),
        path(f"{prefix}metrics", metrics),
    ]
