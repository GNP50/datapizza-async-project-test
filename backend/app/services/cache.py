from typing import Any
import json
import redis.asyncio as aioredis
from app.core.config import get_settings


class CacheManager:
    def __init__(self):
        self.settings = get_settings()
        self.redis: aioredis.Redis | None = None
        self.default_ttl = self.settings.cache_ttl

    async def connect(self):
        self.redis = await aioredis.from_url(
            self.settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )

    async def disconnect(self):
        if self.redis:
            await self.redis.close()

    async def get(self, key: str) -> Any | None:
        if not self.redis:
            return None

        value = await self.redis.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if not self.redis:
            return False

        if ttl is None:
            ttl = self.default_ttl

        if not isinstance(value, str):
            value = json.dumps(value)

        return await self.redis.setex(key, ttl, value)

    async def delete(self, key: str) -> bool:
        if not self.redis:
            return False
        return await self.redis.delete(key) > 0

    async def exists(self, key: str) -> bool:
        if not self.redis:
            return False
        return await self.redis.exists(key) > 0

    async def clear_pattern(self, pattern: str) -> int:
        if not self.redis:
            return 0

        keys = await self.redis.keys(pattern)
        if keys:
            return await self.redis.delete(*keys)
        return 0


cache_manager = CacheManager()
