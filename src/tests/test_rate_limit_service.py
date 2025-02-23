"""Test the RateLimitService class."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from redis.exceptions import RedisError

from src.services.rate_limit_service import RateLimitService


@pytest.fixture
def rate_limit_service():
    """Create RateLimitService with mocked Redis."""
    service = RateLimitService()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="0")
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.delete = AsyncMock()
    service.redis = mock_redis
    return service


@pytest.mark.asyncio
async def test_record_failed_login(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test recording failed login attempts."""
    email = "test@example.com"
    expected_key = f"failed_login:{email}"

    await rate_limit_service.record_failed_login(email)

    rate_limit_service.redis.incr.assert_called_once_with(expected_key)
    rate_limit_service.redis.expire.assert_called_once_with(expected_key, 1800)


@pytest.mark.asyncio
async def test_multiple_failed_attempts(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test multiple failed login attempts."""
    email = "test@example.com"

    # Simulate 3 failed attempts
    rate_limit_service.redis.incr.side_effect = [1, 2, 3]
    rate_limit_service.redis.get.return_value = "3"

    for i in range(3):
        await rate_limit_service.record_failed_login(email)
        # Verify increment and expiry set each time
        assert rate_limit_service.redis.incr.call_count == i + 1
        assert rate_limit_service.redis.expire.call_count == i + 1

    attempts = await rate_limit_service.get_failed_attempts(email)
    assert attempts == 3


@pytest.mark.asyncio
async def test_check_failed_attempts(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test rate limiting check."""
    email = "test@example.com"
    expected_key = f"failed_login:{email}"

    # Test under limit
    rate_limit_service.redis.get.return_value = "2"
    await rate_limit_service.check_failed_attempts(email)
    rate_limit_service.redis.get.assert_called_with(expected_key)

    # Test at limit
    rate_limit_service.redis.get.return_value = "5"
    with pytest.raises(HTTPException) as exc:
        await rate_limit_service.check_failed_attempts(email)
    assert exc.value.status_code == 429
    assert "Too many failed attempts" in exc.value.detail


@pytest.mark.asyncio
async def test_clear_failed_attempts(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test clearing failed login attempts."""
    email = "test@example.com"
    expected_key = f"failed_login:{email}"

    await rate_limit_service.clear_failed_attempts(email)
    rate_limit_service.redis.delete.assert_called_once_with(expected_key)


@pytest.mark.asyncio
async def test_no_failed_attempts(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test getting attempts for user with no failures."""
    email = "new@example.com"
    attempts = await rate_limit_service.get_failed_attempts(email)
    assert attempts == 0


@pytest.mark.asyncio
async def test_failed_attempts_ttl(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test that failed attempts expire after TTL."""
    email = "test@example.com"
    await rate_limit_service.record_failed_login(email)

    # Mock Redis TTL expiration
    rate_limit_service.redis.get = AsyncMock(return_value=None)
    attempts = await rate_limit_service.get_failed_attempts(email)
    assert attempts == 0


@pytest.mark.asyncio
async def test_redis_connection_error(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test handling of Redis connection errors."""
    email = "test@example.com"
    rate_limit_service.redis.incr = AsyncMock(side_effect=RedisError)

    # Should not raise error but log it
    await rate_limit_service.record_failed_login(email)
    attempts = await rate_limit_service.get_failed_attempts(email)
    assert attempts == 0


@pytest.mark.asyncio
async def test_check_failed_attempts_at_limit(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test rate limiting after max attempts."""
    email = "test@example.com"

    # Mock 5 failed attempts
    rate_limit_service.redis.get = AsyncMock(return_value="5")

    with pytest.raises(HTTPException) as exc:
        await rate_limit_service.check_failed_attempts(email)
    assert exc.value.status_code == 429
    assert "Account locked for 30 minutes" in exc.value.detail


@pytest.mark.asyncio
async def test_record_failed_login_sets_expiry(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test that failed login attempts expire after 30 minutes."""
    email = "test@example.com"
    expected_key = f"failed_login:{email}"

    await rate_limit_service.record_failed_login(email)

    rate_limit_service.redis.incr.assert_called_once_with(expected_key)
    rate_limit_service.redis.expire.assert_called_once_with(expected_key, 1800)  # 30 minutes


@pytest.mark.asyncio
async def test_failed_attempts_reset_after_expiry(rate_limit_service):  # pylint: disable=redefined-outer-name
    """Test that attempts reset after Redis key expires."""
    email = "test@example.com"

    # First check shows attempts
    rate_limit_service.redis.get = AsyncMock(return_value="3")
    attempts = await rate_limit_service.get_failed_attempts(email)
    assert attempts == 3

    # After expiry, should return 0
    rate_limit_service.redis.get = AsyncMock(return_value=None)
    attempts = await rate_limit_service.get_failed_attempts(email)
    assert attempts == 0
