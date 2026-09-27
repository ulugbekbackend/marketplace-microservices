"""Redis storage for carts and favorites.

    cart:user:{user_id}          hash {variant_id: qty}
    cart:guest:{guest_id}        hash {variant_id: qty}
    cart:<owner>:prices          hash {variant_id: price_tiyin the customer last saw}
    fav:user:{user_id}           set {product_id}

Both cart hashes expire together; every write pushes the TTL forward.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class CartOwner:
    kind: str  # "user" | "guest"
    id: UUID

    @classmethod
    def user(cls, user_id: UUID) -> "CartOwner":
        return cls("user", user_id)

    @classmethod
    def guest(cls, guest_id: UUID) -> "CartOwner":
        return cls("guest", guest_id)

    @property
    def items_key(self) -> str:
        return f"cart:{self.kind}:{self.id}"

    @property
    def prices_key(self) -> str:
        return f"{self.items_key}:prices"


@dataclass(frozen=True, slots=True)
class StoredLine:
    variant_id: UUID
    qty: int
    seen_price_tiyin: int | None


class CartStore:
    def __init__(self, redis: Redis, *, ttl_seconds: int, max_qty: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._max_qty = max_qty

    async def lines(self, owner: CartOwner) -> list[StoredLine]:
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.hgetall(owner.items_key)
            pipe.hgetall(owner.prices_key)
            raw_items, raw_prices = await pipe.execute()
        lines = []
        for raw_id, raw_qty in raw_items.items():
            price = raw_prices.get(raw_id)
            lines.append(
                StoredLine(UUID(raw_id), int(raw_qty), int(price) if price is not None else None)
            )
        return sorted(lines, key=lambda line: str(line.variant_id))

    async def quantity(self, owner: CartOwner, variant_id: UUID) -> int:
        raw = await self._redis.hget(owner.items_key, str(variant_id))
        return int(raw) if raw is not None else 0

    async def count_lines(self, owner: CartOwner) -> int:
        return int(await self._redis.hlen(owner.items_key))

    async def set_line(self, owner: CartOwner, variant_id: UUID, qty: int, price: int) -> None:
        """Store the quantity and the price the customer saw at that moment."""
        field = str(variant_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(owner.items_key, field, min(qty, self._max_qty))
            pipe.hset(owner.prices_key, field, price)
            self._touch(pipe, owner)
            await pipe.execute()

    async def remove(self, owner: CartOwner, *variant_ids: UUID) -> None:
        if not variant_ids:
            return
        fields = [str(variant_id) for variant_id in variant_ids]
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hdel(owner.items_key, *fields)
            pipe.hdel(owner.prices_key, *fields)
            self._touch(pipe, owner)
            await pipe.execute()

    async def clear(self, owner: CartOwner) -> None:
        await self._redis.delete(owner.items_key, owner.prices_key)

    async def merge(self, source: CartOwner, target: CartOwner) -> None:
        """Move the source cart into the target: quantities add up, capped at the maximum.

        The price the target already saw wins, so a price change is still reported.
        """
        source_lines = await self.lines(source)
        if not source_lines:
            return
        target_lines = {line.variant_id: line for line in await self.lines(target)}
        async with self._redis.pipeline(transaction=True) as pipe:
            for line in source_lines:
                field = str(line.variant_id)
                existing = target_lines.get(line.variant_id)
                qty = line.qty + (existing.qty if existing else 0)
                pipe.hset(target.items_key, field, min(qty, self._max_qty))
                price = existing.seen_price_tiyin if existing else None
                if price is None:
                    price = line.seen_price_tiyin
                if price is not None:
                    pipe.hset(target.prices_key, field, price)
            self._touch(pipe, target)
            pipe.delete(source.items_key, source.prices_key)
            await pipe.execute()

    def _touch(self, pipe: Any, owner: CartOwner) -> None:
        pipe.expire(owner.items_key, self._ttl)
        pipe.expire(owner.prices_key, self._ttl)


class FavoritesStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(user_id: UUID) -> str:
        return f"fav:user:{user_id}"

    async def list(self, user_id: UUID) -> list[UUID]:
        members = await self._redis.smembers(self._key(user_id))
        return sorted((UUID(str(member)) for member in members), key=str)

    async def count(self, user_id: UUID) -> int:
        return int(await self._redis.scard(self._key(user_id)))

    async def contains(self, user_id: UUID, product_id: UUID) -> bool:
        return bool(await self._redis.sismember(self._key(user_id), str(product_id)))

    async def add(self, user_id: UUID, product_id: UUID) -> None:
        await self._redis.sadd(self._key(user_id), str(product_id))

    async def remove(self, user_id: UUID, product_id: UUID) -> None:
        await self._redis.srem(self._key(user_id), str(product_id))
