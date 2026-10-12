"""Full reindex from the catalog with an atomic alias swap."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from app import reindex as reindex_cli
from app.services.catalog import CatalogClient, CatalogUnavailableError
from app.services.index import ProductIndex, epoch_millis
from app.services.reindex import Reindexer, ReindexJob
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import (
    FakeCatalog,
    FakeRedis,
    closed_port_url,
    make_product,
    make_settings,
    seed,
)

REINDEX_URL = "/internal/search/reindex"


def documents(count: int, **kwargs: Any) -> list[dict[str, Any]]:
    return [make_product(**kwargs).model_dump(mode="json") for _ in range(count)]


async def reindex(client: AsyncClient, app: FastAPI) -> dict[str, Any]:
    """Start a reindex through the API, wait for it and return the job report."""
    started = await client.post(REINDEX_URL)
    assert started.status_code == 202, started.text
    assert started.json()["status"] == "running"
    await app.state.reindexer.wait()
    response = await client.get(REINDEX_URL)
    assert response.status_code == 200, response.text
    job: dict[str, Any] = response.json()
    assert job["job_id"] == started.json()["job_id"]
    return job


async def count(index: ProductIndex) -> int:
    response = await index.es.count(index=index.alias)
    total: int = response["count"]
    return total


async def test_reindex_builds_a_new_index_and_swaps_the_alias(
    client: AsyncClient, app: FastAPI, index: ProductIndex, catalog: FakeCatalog
) -> None:
    await seed(index, [make_product(title="Gone from the catalog")])
    old = (await index.targets()).live
    catalog.documents = documents(3)

    job = await reindex(client, app)

    assert job["status"] == "done"
    assert job["finished_at"] is not None
    body = job["result"]
    assert body["indexed"] == 3
    assert (body["stale"], body["skipped"]) == (0, 0)
    assert body["removed_indices"] == old
    targets = await index.targets()
    assert targets.live == [body["index"]]
    assert targets.pending == []
    assert await index.all_indices() == [body["index"]]
    assert await count(index) == 3


async def test_reindex_without_existing_index(
    client: AsyncClient, app: FastAPI, index: ProductIndex, catalog: FakeCatalog
) -> None:
    catalog.documents = documents(2)

    body = (await reindex(client, app))["result"]

    assert body["removed_indices"] == []
    assert await count(index) == 2


async def test_reindex_pages_through_the_catalog(
    index: ProductIndex, catalog: FakeCatalog, redis: FakeRedis
) -> None:
    catalog.documents = documents(5)
    http = httpx.AsyncClient(
        base_url="http://catalog", transport=httpx.MockTransport(catalog.handle)
    )
    reindexer = Reindexer(index, CatalogClient(http, page_size=2), redis)

    result = await reindexer.run()
    await http.aclose()

    assert result.indexed == 5
    assert [request["page"] for request in catalog.requests] == ["1", "2", "3"]
    assert await count(index) == 5


async def test_empty_catalog_gives_an_empty_index(
    client: AsyncClient, app: FastAPI, index: ProductIndex, catalog: FakeCatalog
) -> None:
    body = (await reindex(client, app))["result"]

    assert body["indexed"] == 0
    assert len(catalog.requests) == 1
    assert await count(index) == 0


async def test_invalid_documents_are_skipped(
    client: AsyncClient, app: FastAPI, index: ProductIndex, catalog: FakeCatalog
) -> None:
    catalog.documents = [*documents(2), {"product_id": "broken"}]

    body = (await reindex(client, app))["result"]

    assert (body["indexed"], body["skipped"]) == (2, 1)


async def test_catalog_failure_keeps_the_live_index(
    client: AsyncClient, app: FastAPI, redis: FakeRedis, index: ProductIndex, catalog: FakeCatalog
) -> None:
    await seed(index, [make_product()])
    live = await index.all_indices()
    catalog.status = 502

    job = await reindex(client, app)

    assert job["status"] == "failed"
    assert job["error_code"] == "CATALOG_UNAVAILABLE"
    assert job["result"] is None
    assert app.state.reindexer.lock_key not in redis.data
    assert await index.all_indices() == live  # the half built index is dropped
    assert await count(index) == 1


async def test_garbage_from_the_catalog_is_a_catalog_failure(index: ProductIndex) -> None:
    http = httpx.AsyncClient(
        base_url="http://catalog",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<html>")),
    )
    pages = CatalogClient(http).pages()

    with pytest.raises(CatalogUnavailableError):
        await anext(pages)
    await http.aclose()


async def test_only_one_reindex_at_a_time(
    client: AsyncClient, app: FastAPI, redis: FakeRedis, index: ProductIndex
) -> None:
    redis.data[app.state.reindexer.lock_key] = "someone else"

    response = await client.post(REINDEX_URL)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REINDEX_IN_PROGRESS"
    assert redis.data[app.state.reindexer.lock_key] == "someone else"


async def test_lock_is_released_after_a_run(
    client: AsyncClient, app: FastAPI, redis: FakeRedis, index: ProductIndex
) -> None:
    await reindex(client, app)

    assert app.state.reindexer.lock_key not in redis.data


async def test_events_during_reindex_survive_the_swap(
    client: AsyncClient, app: FastAPI, index: ProductIndex, catalog: FakeCatalog
) -> None:
    """An update that lands while the catalog is being read is not lost, and the reindex
    does not overwrite it with the older catalog copy."""
    await index.ensure()
    product = make_product(title="Catalog copy")
    catalog.documents = [product.model_dump(mode="json")]
    newer = product.model_copy(update={"title": "Edited during reindex"})
    added = make_product(title="Created during reindex")

    async def on_page(page: int) -> None:
        await index.upsert(newer, version=epoch_millis(product.updated_at) + 1)
        await index.upsert(added, version=epoch_millis(added.updated_at))

    catalog.on_page = on_page

    body = (await reindex(client, app))["result"]

    assert body["stale"] == 1
    await index.refresh()
    hits = await index.es.search(index=index.alias, query={"match_all": {}})
    titles = {hit["_source"]["title"] for hit in hits["hits"]["hits"]}
    assert titles == {"Edited during reindex", "Created during reindex"}


async def test_cli_reindex(
    index: ProductIndex, catalog: FakeCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog.documents = documents(2)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.reindex.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(catalog.handle), **kwargs),
    )
    monkeypatch.setattr("app.reindex.Redis.from_url", lambda *args, **kwargs: FakeRedis())

    assert await reindex_cli.run(make_settings(index.alias)) == 0
    assert await count(index) == 2


async def test_cli_reports_failure(index: ProductIndex, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.reindex.Redis.from_url", lambda *args, **kwargs: FakeRedis())
    settings = make_settings(index.alias, catalog_url=closed_port_url())

    assert await reindex_cli.run(settings) == 1
    assert await index.all_indices() == []


async def test_no_reindex_yet_is_404(client: AsyncClient, index: ProductIndex) -> None:
    response = await client.get(REINDEX_URL)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_a_running_reindex_is_reported_and_blocks_another(
    client: AsyncClient, app: FastAPI, index: ProductIndex, catalog: FakeCatalog
) -> None:
    catalog.documents = documents(1)
    release = asyncio.Event()

    async def on_page(page: int) -> None:
        await release.wait()

    catalog.on_page = on_page

    started = (await client.post(REINDEX_URL)).json()
    for _ in range(100):  # let the job reach the catalog
        if catalog.requests:
            break
        await asyncio.sleep(0.01)
    running = (await client.get(REINDEX_URL)).json()
    second = await client.post(REINDEX_URL)
    release.set()
    await app.state.reindexer.wait()

    assert running["status"] == "running"
    assert running["job_id"] == started["job_id"]
    assert running["finished_at"] is None
    assert second.status_code == 409
    assert (await client.get(REINDEX_URL)).json()["status"] == "done"


async def test_a_job_whose_process_died_reads_as_interrupted(
    client: AsyncClient, app: FastAPI, redis: FakeRedis, index: ProductIndex
) -> None:
    reindexer = app.state.reindexer
    job = ReindexJob(job_id="lost", status="running", started_at=datetime.now(UTC))
    redis.data[reindexer.status_key] = job.to_json()  # the lock expired with the process

    body = (await client.get(REINDEX_URL)).json()

    assert body["status"] == "failed"
    assert body["error_code"] == "REINDEX_INTERRUPTED"


async def test_shutdown_interrupts_a_running_reindex(
    app: FastAPI, redis: FakeRedis, index: ProductIndex, catalog: FakeCatalog
) -> None:
    catalog.documents = documents(1)
    blocked = asyncio.Event()

    async def on_page(page: int) -> None:
        await blocked.wait()

    catalog.on_page = on_page
    reindexer = app.state.reindexer
    await reindexer.start()
    for _ in range(100):
        if catalog.requests:
            break
        await asyncio.sleep(0.01)

    await reindexer.aclose()

    status = await reindexer.status()
    assert status is not None
    assert (status.status, status.error_code) == ("failed", "REINDEX_INTERRUPTED")
    assert reindexer.lock_key not in redis.data
    assert await index.all_indices() == []  # the half built index is dropped


async def test_reindex_keeps_tombstones_so_a_late_update_stays_deleted(
    client: AsyncClient, app: FastAPI, index: ProductIndex, catalog: FakeCatalog
) -> None:
    await index.ensure()
    deleted = make_product(title="Deleted product")
    deleted_at = epoch_millis(deleted.updated_at) + 1000
    await index.upsert(deleted, version=epoch_millis(deleted.updated_at))
    await index.delete(deleted.product_id, version=deleted_at)
    kept = make_product(title="Kept product")
    catalog.documents = [kept.model_dump(mode="json")]

    body = (await reindex(client, app))["result"]

    assert body["tombstones"] == 1
    # The update that came before the delete arrives again, long after it.
    assert await index.upsert(deleted, version=epoch_millis(deleted.updated_at)) is False
    await index.refresh()
    hits = await index.es.search(index=index.alias, query={"match_all": {}})
    assert {hit["_id"] for hit in hits["hits"]["hits"]} == {
        str(kept.product_id),
        str(deleted.product_id),  # the tombstone
    }
