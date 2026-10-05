"""Settings read once from the environment (``.env`` is found by decouple)."""

from dataclasses import dataclass

from decouple import config


@dataclass(frozen=True, slots=True)
class Settings:
    elasticsearch_url: str
    elasticsearch_timeout: float
    index_alias: str
    index_shards: int
    index_replicas: int
    redis_url: str
    rabbitmq_url: str
    consumer_enabled: bool
    catalog_url: str
    catalog_timeout: float
    reindex_page_size: int
    reindex_lock_seconds: int


def load_settings() -> Settings:
    return Settings(
        elasticsearch_url=config("ELASTICSEARCH_URL", default="http://elasticsearch:9200"),
        elasticsearch_timeout=config("ELASTICSEARCH_TIMEOUT", default=5.0, cast=float),
        index_alias=config("SEARCH_INDEX_ALIAS", default="products"),
        index_shards=config("SEARCH_INDEX_SHARDS", default=1, cast=int),
        index_replicas=config("SEARCH_INDEX_REPLICAS", default=0, cast=int),
        redis_url=config("REDIS_URL", default="redis://redis:6379/0"),
        rabbitmq_url=config("RABBITMQ_URL", default=""),
        consumer_enabled=config("SEARCH_CONSUMER_ENABLED", default=True, cast=bool),
        catalog_url=config("CATALOG_INTERNAL_URL", default="http://catalog:8000"),
        catalog_timeout=config("CATALOG_TIMEOUT", default=10.0, cast=float),
        reindex_page_size=config("SEARCH_REINDEX_PAGE_SIZE", default=200, cast=int),
        reindex_lock_seconds=config("SEARCH_REINDEX_LOCK_SECONDS", default=3600, cast=int),
    )
