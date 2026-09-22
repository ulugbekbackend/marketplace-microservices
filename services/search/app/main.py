"""Search service: skeleton with health, metrics and structured logging."""

from decouple import config
from fastapi import FastAPI

from py_common.health import HealthRegistry, tcp_check
from py_common.logging import configure_logging
from py_common.web.fastapi import setup

SERVICE_NAME = "search"
API_PREFIX = "/api/search"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))


def build_registry() -> HealthRegistry:
    """Dependencies this service needs before it can serve traffic."""
    registry = HealthRegistry()
    registry.add(
        "rabbitmq",
        tcp_check(
            config("RABBITMQ_HOST", default="rabbitmq"),
            config("RABBITMQ_PORT", default=5672, cast=int),
        ),
    )
    return registry


def create_app() -> FastAPI:
    app = FastAPI(
        title="Search service",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
    )
    setup(app, registry=build_registry(), api_prefix=API_PREFIX)
    return app


app = create_app()
