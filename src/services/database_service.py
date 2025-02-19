"""Database service for user management."""

from typing import Awaitable, Dict, Optional, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.utils import logger
from src.utils.config import REDIS_DB, REDIS_HOST, REDIS_PORT


class DatabaseService:
    """Handles database operations for users."""

    def __init__(self):
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    async def get_user(self, email: str) -> Optional[Dict[str, str]]:
        """Get user from Redis."""
        user_data = await cast(Awaitable[Dict[str, str]], self.redis.hgetall(f"user:{email}"))
        return user_data if user_data else None

    async def create_user(self, user_data: Dict) -> bool:
        """Create user in Redis."""
        try:
            email = user_data["email"]
            await cast(Awaitable[int], self.redis.hset(f"user:{email}", mapping=user_data))
            return True
        except RedisError as e:
            logger.error("❌ Database error: %s", str(e))
            return False

    async def record_failed_login(self, email: str) -> None:
        """Record failed login attempt."""
        key = f"failed_login:{email}"
        await self.redis.incr(key)
        await self.redis.expire(key, 1800)  # 30 minutes

    async def get_failed_attempts(self, email: str) -> int:
        """Get number of failed login attempts."""
        key = f"failed_login:{email}"
        attempts = await self.redis.get(key)
        return int(attempts) if attempts else 0

    async def clear_failed_attempts(self, email: str) -> None:
        """Clear failed login attempts."""
        key = f"failed_login:{email}"
        await self.redis.delete(key)
