"""Redis service for caching search results and managing rate limits."""

import json
from typing import Any, Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.utils import logger
from src.utils.config import CACHE_TTL, REDIS_DB, REDIS_HOST, REDIS_PORT


class RedisService:
    """
    Service for Redis caching and data storage.

    Attributes:
        redis: Async Redis client
        cache_ttl: Time-to-live for cached items in seconds
    """

    def __init__(self):
        """Initialize Redis connection with configuration."""
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        self.cache_ttl = CACHE_TTL

    async def get_cache(self, key: str) -> Optional[Any]:
        """
        Retrieve cached data by key.

        Args:
            key: Cache key to lookup

        Returns:
            Optional[Any]: Cached data if exists, None otherwise
        """
        try:
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except json.JSONDecodeError as e:
            logger.error("❌ Redis JSON decode error: %s", str(e))
            return None
        except RedisError as e:
            logger.error("❌ Redis connection error: %s", str(e))
            return None

    async def set_cache(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store data in cache with expiration.

        Args:
            key: Cache key
            value: Data to cache
            ttl: Optional custom time-to-live in seconds (overrides default)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            expiry = ttl if ttl is not None else self.cache_ttl
            await self.redis.setex(key, expiry, json.dumps(value))
            return True
        except TypeError as e:  # json.dumps() raises TypeError for encoding errors
            logger.error("❌ Redis JSON encode error: %s", str(e))
            return False
        except RedisError as e:
            logger.error("❌ Redis connection error: %s", str(e))
            return False

    async def delete_cache(self, key: str):
        """Remove a key from Redis cache."""
        await self.redis.delete(key)
