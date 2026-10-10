"""Prometheus exposition shared by the services.

Gunicorn runs several worker processes, each with its own counters; with
``PROMETHEUS_MULTIPROC_DIR`` set they write to that directory and ``latest()`` adds them up.
Background workers (consumers, relays) have no web server: ``serve(port)`` gives them one.
"""

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    generate_latest,
    multiprocess,
    start_http_server,
)

MULTIPROC_ENV = "PROMETHEUS_MULTIPROC_DIR"

__all__ = ["CONTENT_TYPE_LATEST", "child_exit", "latest", "serve"]


def latest() -> bytes:
    """The current metrics in the text format, summed over workers when multiprocess."""
    if os.environ.get(MULTIPROC_ENV):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return generate_latest(registry)
    return generate_latest(REGISTRY)


def child_exit(server: object, worker: object) -> None:
    """Gunicorn hook: forget the live gauges of a worker that exited."""
    if os.environ.get(MULTIPROC_ENV):
        multiprocess.mark_process_dead(worker.pid)  # type: ignore[attr-defined,no-untyped-call]


def serve(port: int) -> None:
    """Expose /metrics of a process without a web server (a no-op for port 0)."""
    if port:
        start_http_server(port)
