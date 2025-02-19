"""Service for handling rate limiting using Redis."""

from redis.asyncio import Redis

from src.utils.config import REDIS_DB, REDIS_HOST, REDIS_PORT


class RateLimitService:
    """Handles rate limiting using Redis for login attempts."""

    def __init__(self):
        """Initialize Redis connection."""
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    async def record_failed_login(self, email: str) -> None:
        """
        Record a failed login attempt with 30-minute expiry.

        Args:
            email: User's email address
        """
        key = f"failed_login:{email}"
        await self.redis.incr(key)
        await self.redis.expire(key, 1800)  # 30 minutes

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
