"""Service for handling rate limiting using Redis."""

from fastapi import HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.utils import logger


class RateLimitService:
    """Handles rate limiting using Redis."""

    def __init__(self, redis_client: Redis):
        """Initialize with a Redis client instance."""
        self.redis = redis_client
        self.max_attempts = 5  # Lock after 5 failed attempts
        self.reset_after = 1800  # 30 minutes lock duration

    async def check_failed_attempts(self, email: str) -> None:
        """Check if too many recent failed attempts."""
        attempts = 0  # Default to 0 in case of issues with the method itself before try-except
        try:
            attempts = await self.get_failed_attempts(email)
        except Exception as e:  # Broad catch if get_failed_attempts itself fails unexpectedly
            logger.error(f"Error calling get_failed_attempts for {email}: {e}")
            # Depending on policy, you might allow login or deny. Denying is safer.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error checking login attempts.")

        if attempts >= self.max_attempts:
            logger.warning(f"Rate limit triggered for {email} after {attempts} attempts.")
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
            int: Number of failed attempts, or 0 if error or not found.
        """
        key = f"failed_login:{email}"
        try:
            attempts_raw = await self.redis.get(key)
            if attempts_raw:
                return int(attempts_raw)  # attempts_raw is bytes, decode if necessary or int() handles it
            return 0  # Key not found or empty
        except RedisError as e:
            logger.error("❌ Redis error getting failed attempts for %s: %s", email, str(e))
            return 0  # Return 0 on Redis error as per test expectation
        except ValueError as e:  # If int() conversion fails for some reason
            logger.error("❌ Error converting stored failed attempts to int for %s: %s. Value: '%s'", email, e, attempts_raw)
            return 0  # Or handle as a more severe error, potentially by deleting the corrupt key

    async def clear_failed_attempts(self, email: str) -> None:
        """
        Clear failed login attempts for a user.

        Args:
            email: User's email address
        """
        key = f"failed_login:{email}"
        await self.redis.delete(key)
