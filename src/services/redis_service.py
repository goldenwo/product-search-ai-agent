import redis
import json
from src.utils.config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_TTL

class RedisService:
    """Handles Redis caching for product searches."""
    
    def __init__(self):
        self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    def get_cache(self, key: str):
        """Retrieve cached data from Redis."""
        cached_data = self.client.get(key)
        return json.loads(cached_data) if cached_data else None

    def set_cache(self, key: str, data: dict, ttl: int = REDIS_TTL):
        """Set data in Redis cache with a time-to-live (TTL)."""
        self.client.setex(key, ttl, json.dumps(data))

    def delete_cache(self, key: str):
        """Remove a key from the Redis cache."""
        self.client.delete(key)
