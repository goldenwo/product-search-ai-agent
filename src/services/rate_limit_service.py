"""Service for handling rate limiting using Redis."""

from fastapi import HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.utils import REDIS_DB, REDIS_HOST, REDIS_PORT, logger


class RateLimitService:
    """Handles rate limiting using Redis."""

    def __init__(self):
        """Initialize Redis connection."""
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        self.max_attempts = 5  # Lock after 5 failed attempts
        self.reset_after = 1800  # 30 minutes lock duration

    async def check_failed_attempts(self, email: str) -> None:
        """Check if too many recent failed attempts."""
        attempts = await self.get_failed_attempts(email)
        if attempts >= self.max_attempts:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts. Account locked for 30 minutes.")

    async def record_failed_login(self, email: str) -> None:
        """
        Record a failed login attempt with 30-minute expiry.

        Args:
            email: User's email address
        """
        key = f"failed_login:{email}"
        try:
            await self.redis.incr(key)
            await self.redis.expire(key, self.reset_after)  # Auto-expire after 30 minutes
        except RedisError as e:
            logger.error("❌ Redis error recording failed login: %s", str(e))

    async def get_failed_attempts(self, email: str) -> int:
        """
        Get number of failed login attempts for a user.

        Args:
            email: User's email address

        Returns:
            int: Number of failed attempts
        """
        key = f"failed_login:{email}"
        attempts = await self.redis.get(key)
        return int(attempts) if attempts else 0

    async def clear_failed_attempts(self, email: str) -> None:
        """
        Clear failed login attempts for a user.

        Args:
            email: User's email address
        """
        key = f"failed_login:{email}"
        await self.redis.delete(key)
