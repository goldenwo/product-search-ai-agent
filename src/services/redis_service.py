"""Redis caching service for storing and retrieving product search results."""

import json
from typing import Dict, List, Union

from redis.asyncio import Redis

from src.utils import logger
from src.utils.config import REDIS_DB, REDIS_HOST, REDIS_PORT, REDIS_TTL


class RedisService:
    """Handles Redis caching for product searches."""

    def __init__(self):
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    async def get_cache(self, key: str):
        """Retrieve cached data from Redis."""
        cached_data = await self.redis.get(key)
        if not cached_data:
            return None
        try:
            return json.loads(str(cached_data))
        except json.JSONDecodeError:
            logger.error("❌ Invalid JSON in cache for key: %s", key)
            return None

    async def set_cache(self, key: str, data: Union[Dict, List], ttl: int = REDIS_TTL):
        """Set data in Redis cache with TTL."""
        if not isinstance(data, (dict, list)):
            logger.error("❌ Invalid data type for cache: %s", type(data))
            return
        if ttl <= 0:
            logger.error("❌ Invalid TTL value: %d", ttl)
            return
        await self.redis.setex(key, ttl, json.dumps(data))

    async def delete_cache(self, key: str):
        """Remove a key from Redis cache."""
        await self.redis.delete(key)
