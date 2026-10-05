"""Index lifecycle and versioned writes."""

from datetime import timedelta
from typing import Any

import pytest
from app.services.analysis import INDEX_MAPPINGS, REFRESH_INTERVAL
from app.services.index import (
    BulkLoadError,
    IndexMissingError,
    ProductIndex,
    WriteTargets,
    epoch_millis,
    to_document,
)
from elasticsearch import AsyncElasticsearch

from tests.conftest import BASE_TIME, make_product


async def get_source(index: ProductIndex, product_id: Any) -> dict[str, Any] | None:
    response = await index.es.options(ignore_status=404).get(index=index.alias, id=str(product_id))
    if not response.body.get("found"):
        return None
    source: dict[str, Any] = response.body["_source"]
    return source


def test_document_matches_the_mapping() -> None:
    product = make_product(
        attributes=[("color", "Red"), ("color", "Red"), ("size", "M")],
        categories=[],
    )

    document = to_document(product)

    assert set(document) == set(INDEX_MAPPINGS["properties"])
    assert document["attributes"] == [
        {"code": "color", "value": "Red"},
        {"code": "size", "value": "M"},
    ]
    assert document["min_price"] == product.min_price_tiyin


def test_epoch_millis_treats_naive_time_as_utc() -> None:
    aware = BASE_TIME + timedelta(milliseconds=5)

    assert epoch_millis(aware) == epoch_millis(aware.replace(tzinfo=None))
    assert epoch_millis(aware) % 1000 == 5


def test_write_targets_do_not_repeat_an_index() -> None:
    targets = WriteTargets(live=["a"], pending=["a", "b"])

    assert targets.all == ["a", "b"]


async def test_ensure_creates_first_version_behind_alias(index: ProductIndex) -> None:
    created = await index.ensure()

    assert created == f"{index.alias}_v1"
    assert (await index.targets()).live == [created]
    assert await index.ensure() == created  # idempotent


async def refresh_interval(index: ProductIndex, name: str) -> Any:
    settings = await index.es.indices.get_settings(index=name)
    return settings[name]["settings"]["index"].get("refresh_interval")


async def test_refresh_interval_is_explicit_so_idle_shards_keep_refreshing(
    index: ProductIndex,
) -> None:
    created = await index.ensure()
    assert await refresh_interval(index, created) == REFRESH_INTERVAL

    bulk = index.new_index_name()
    await index.create(bulk, bulk=True)
    assert await refresh_interval(index, bulk) == "-1"
    await index.finish_bulk(bulk)
    assert await refresh_interval(index, bulk) == REFRESH_INTERVAL
    await index.es.indices.delete(index=bulk)


async def test_ensure_skips_a_taken_first_name(index: ProductIndex) -> None:
    await index.create(index.first_index_name())  # exists, but not behind the alias

    created = await index.ensure()

    assert created != index.first_index_name()
    assert created.startswith(f"{index.alias}_v")
    assert (await index.targets()).live == [created]


async def test_ensure_tolerates_a_concurrent_creator(
    index: ProductIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = index.create

    async def racing_create(name: str, **kwargs: Any) -> None:
        await original(name, aliases=[index.alias])  # the other replica
        await original(name, **kwargs)  # ours fails: already exists

    monkeypatch.setattr(index, "create", racing_create)

    assert await index.ensure() == index.first_index_name()


async def test_ensure_reraises_other_errors(
    index: ProductIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_create(name: str, **kwargs: Any) -> None:
        await index.es.indices.create(index="Invalid Name")

    monkeypatch.setattr(index, "create", broken_create)

    with pytest.raises(Exception, match="invalid_index_name"):
        await index.ensure()


async def test_upsert_and_read_back(index: ProductIndex) -> None:
    await index.ensure()
    product = make_product(title="Telefon")

    assert await index.upsert(product, version=1000) is True

    source = await get_source(index, product.product_id)
    assert source is not None
    assert source["title"] == "Telefon"


async def test_older_update_is_a_no_op(index: ProductIndex) -> None:
    await index.ensure()
    product = make_product(title="New title")
    await index.upsert(product, version=2000)

    stale = product.model_copy(update={"title": "Old title"})
    assert await index.upsert(stale, version=1000) is False

    source = await get_source(index, product.product_id)
    assert source is not None
    assert source["title"] == "New title"


async def test_same_version_is_reapplied(index: ProductIndex) -> None:
    await index.ensure()
    product = make_product()

    assert await index.upsert(product, version=2000) is True
    assert await index.upsert(product, version=2000) is True


async def test_delete_and_stale_delete(index: ProductIndex) -> None:
    await index.ensure()
    product = make_product()
    await index.upsert(product, version=2000)

    assert await index.delete(product.product_id, version=1000) is False
    assert await get_source(index, product.product_id) is not None

    assert await index.delete(product.product_id, version=3000) is True
    assert await get_source(index, product.product_id) is None


async def test_delete_of_unknown_product_is_fine(index: ProductIndex) -> None:
    await index.ensure()

    assert await index.delete(make_product().product_id, version=1000) is True


async def test_update_older_than_a_delete_does_not_resurrect(index: ProductIndex) -> None:
    await index.ensure()
    product = make_product()
    await index.upsert(product, version=1000)
    await index.delete(product.product_id, version=3000)

    assert await index.upsert(product, version=2000) is False
    assert await get_source(index, product.product_id) is None


async def test_writes_without_index_fail(index: ProductIndex) -> None:
    with pytest.raises(IndexMissingError):
        await index.upsert(make_product(), version=1)
    with pytest.raises(IndexMissingError):
        await index.delete(make_product().product_id, version=1)


async def test_writes_reach_the_pending_index_too(index: ProductIndex) -> None:
    live = await index.ensure()
    pending = index.new_index_name()
    await index.create(pending, aliases=[index.pending_alias])
    product = make_product()

    await index.upsert(product, version=1000)

    for name in (live, pending):
        found = await index.es.get(index=name, id=str(product.product_id))
        assert found["found"] is True


async def test_bulk_load_counts_stale_documents(index: ProductIndex) -> None:
    name = await index.ensure()
    fresh = make_product()
    newer_elsewhere = make_product(updated_at=BASE_TIME)
    await index.upsert(newer_elsewhere, version=epoch_millis(BASE_TIME) + 1)

    stats = await index.bulk_load(name, [fresh, newer_elsewhere])

    assert (stats.indexed, stats.stale) == (1, 1)
    assert (await index.bulk_load(name, [])).indexed == 0


async def test_bulk_load_reports_rejected_documents(
    index: ProductIndex, es: AsyncElasticsearch
) -> None:
    name = await index.ensure()
    await es.indices.put_settings(index=name, settings={"index.blocks.write": True})
    try:
        with pytest.raises(BulkLoadError):
            await index.bulk_load(name, [make_product()])
    finally:
        await es.indices.put_settings(index=name, settings={"index.blocks.write": False})
