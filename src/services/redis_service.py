"""Redis caching service for storing and retrieving product search results."""

import json
from typing import Dict, List, Union

import redis

from src.utils import logger
from src.utils.config import REDIS_DB, REDIS_HOST, REDIS_PORT, REDIS_TTL


class RedisService:
    """Handles Redis caching for product searches."""

    def __init__(self):
        self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    def get_cache(self, key: str):
        """Retrieve cached data from Redis."""
        cached_data = self.client.get(key)
        if not cached_data:
            return None
        try:
            return json.loads(str(cached_data))
        except json.JSONDecodeError:
            logger.error("❌ Invalid JSON in cache for key: %s", key)
            return None

    def set_cache(self, key: str, data: Union[Dict, List], ttl: int = REDIS_TTL):
        """Set data in Redis cache with a time-to-live (TTL)."""
        if not isinstance(data, (dict, list)):
            logger.error("❌ Invalid data type for cache: %s", type(data))
            return
        if ttl <= 0:
            logger.error("❌ Invalid TTL value: %d", ttl)
            return
        self.client.setex(key, ttl, json.dumps(data))

    def delete_cache(self, key: str):
        """Remove a key from the Redis cache."""
        self.client.delete(key)
