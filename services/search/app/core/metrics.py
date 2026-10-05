"""Prometheus metrics of the search service."""

from prometheus_client import Histogram

SEARCH_LATENCY = Histogram(
    "search_latency_seconds",
    "Time spent answering a search request, Elasticsearch round trip included.",
    ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
