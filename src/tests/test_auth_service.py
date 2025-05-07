"""Test the AuthService class."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
import jwt
import pytest

from src.models.user import UserCreate, UserInDB, UserLogin
from src.services.auth_service import AuthService
from src.services.email_service import EmailService
from src.services.redis_service import RedisService
from src.services.user_service import UserService
from src.utils.config import JWT_REFRESH_SECRET_KEY, JWT_SECRET_KEY


@pytest.fixture
def auth_service():
    """Create AuthService with mocked dependencies."""
    # 1. Create mocks for the dependencies
    mock_redis_service = MagicMock(spec=RedisService)
    mock_user_service = MagicMock(spec=UserService)
    mock_email_service = MagicMock(spec=EmailService)

    # Configure sub-mocks if necessary, e.g., mock_redis_service.redis for RateLimitService
    # RateLimitService in AuthService will need a Redis client.
    # AuthService.rate_limit = RateLimitService(redis_client=redis_service.redis)
    # So, mock_redis_service.redis needs to be a mock that RateLimitService can use.
    mock_redis_service.redis = AsyncMock()  # A basic AsyncMock for the redis client itself

    # Mock methods that will be called on these services by AuthService
    # Example for UserService:
    mock_user_service.get_user = AsyncMock(return_value=None)  # Default: user not found
    mock_user_service.create_user = AsyncMock()
    mock_user_service.update_password = AsyncMock()
    mock_user_service.store_email_verification_token = AsyncMock()
    mock_user_service.get_user_email_by_verification_token = AsyncMock(return_value=None)
    mock_user_service.delete_verification_token = AsyncMock()
    mock_user_service.mark_user_as_verified = AsyncMock(return_value=True)

    # Example for RedisService (for JTI denylisting, password reset token checks)
    mock_redis_service.get_cache = AsyncMock(return_value=None)  # Default: JTI not denylisted / token not used
    mock_redis_service.set_cache = AsyncMock()
    mock_redis_service.delete = AsyncMock()  # If used directly

    # Example for EmailService:
    mock_email_service.send_reset_email = AsyncMock(return_value=True)
    mock_email_service.send_password_change_notification = AsyncMock(return_value=True)
    mock_email_service.send_verification_email = AsyncMock(return_value=True)

    # 2. Pass mocks to the AuthService constructor
    service = AuthService(redis_service=mock_redis_service, user_service=mock_user_service, email_service=mock_email_service)
    # The RateLimitService instance within AuthService will now use mock_redis_service.redis
    # You might need to further configure mock_redis_service.redis.get/incr/expire if RateLimitService methods are directly tested via AuthService

    # Return the service and its mocks so tests can configure them further or assert calls
    return service, mock_user_service, mock_redis_service, mock_email_service


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return UserInDB(
        email="test@example.com",
        username="testuser",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY.5ZbR8WyA2b8O",  # 'password123'
    )


def test_password_verification(auth_service):  # pylint: disable=redefined-outer-name
    """Test password verification."""
    service, mock_user_service, _, _ = auth_service
    plain_password = "password123"
    hashed = service.get_password_hash(plain_password)
    assert service.verify_password(plain_password, hashed)
    assert not service.verify_password("wrongpass", hashed)


def test_email_validation(auth_service):  # pylint: disable=redefined-outer-name
    """Test email format validation."""
    service, _, _, _ = auth_service
    assert service.is_valid_email("test@example.com")
    assert not service.is_valid_email("invalid-email")
    assert not service.is_valid_email("@example.com")
    assert not service.is_valid_email("test@.com")


def test_password_strength(auth_service):  # pylint: disable=redefined-outer-name
    """Test password strength requirements."""
    service, _, _, _ = auth_service
    assert service.is_strong_password("Password123")
    assert not service.is_strong_password("password")  # No uppercase/numbers
    assert not service.is_strong_password("12345678")  # No letters
    assert not service.is_strong_password("Pass")  # Too short


@pytest.mark.asyncio
async def test_create_tokens(auth_service):  # pylint: disable=redefined-outer-name
    """Test JWT token creation."""
    service, _, _, _ = auth_service
    email = "test@example.com"
    access_token, refresh_token = await service.create_tokens(email)

    # Verify access token
    access_payload = jwt.decode(access_token, str(JWT_SECRET_KEY), algorithms=["HS256"])
    assert access_payload["sub"] == email
    assert access_payload["type"] == "access"
    assert access_payload["exp"] > datetime.now(timezone.utc).timestamp()

    # Verify refresh token
    refresh_payload = jwt.decode(refresh_token, str(JWT_REFRESH_SECRET_KEY), algorithms=["HS256"])
    assert refresh_payload["sub"] == email
    assert refresh_payload["type"] == "refresh"
    assert refresh_payload["exp"] > datetime.now(timezone.utc).timestamp()


@pytest.mark.asyncio
async def test_refresh_access_token(auth_service):  # pylint: disable=redefined-outer-name
    """Test access token refresh."""
    service, _, _, _ = auth_service
    email = "test@example.com"
    refresh_token = jwt.encode(
        {"sub": email, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}, str(JWT_REFRESH_SECRET_KEY), algorithm="HS256"
    )

    new_token = await service.refresh_access_token(refresh_token)
    assert new_token is not None

    # Verify new token
    payload = jwt.decode(new_token, str(JWT_SECRET_KEY), algorithms=["HS256"])
    assert payload["sub"] == email
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_login_success(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test successful login flow."""
    service, mock_user_service, _, _ = auth_service
    service.authenticate_user = AsyncMock(return_value=mock_user)
    service.rate_limit.check_failed_attempts = AsyncMock()
    service.rate_limit.clear_failed_attempts = AsyncMock()

    login_data = UserLogin(email=mock_user.email, password="password123")
    token = await service.login(login_data)

    assert token.access_token
    assert token.refresh_token
    assert token.token_type == "bearer"
    service.rate_limit.clear_failed_attempts.assert_called_once()


@pytest.mark.asyncio
async def test_login_rate_limit(auth_service):  # pylint: disable=redefined-outer-name
    """Test login rate limiting with 30-minute lockout."""
    # Mock rate limit service to simulate max attempts reached
    service, mock_user_service, _, _ = auth_service
    service.rate_limit.check_failed_attempts = AsyncMock(
        side_effect=HTTPException(status_code=429, detail="Too many failed attempts. Account locked for 30 minutes.")
    )
    service.rate_limit.record_failed_login = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await service.login(UserLogin(email="test@example.com", password="password123"))
    assert exc.value.status_code == 429
    assert "Account locked for 30 minutes" in exc.value.detail


@pytest.mark.asyncio
async def test_login_failure_increments_attempts(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test that failed login increments attempt counter."""
    service, mock_user_service, _, _ = auth_service
    service.authenticate_user = AsyncMock(return_value=None)  # Auth fails
    service.rate_limit.check_failed_attempts = AsyncMock()  # No rate limit yet
    service.rate_limit.record_failed_login = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await service.login(UserLogin(email="test@example.com", password="wrong"))

    assert exc.value.status_code == 401
    service.rate_limit.record_failed_login.assert_called_once()


@pytest.mark.asyncio
async def test_login_success_clears_attempts(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test that successful login clears attempt counter."""
    service, mock_user_service, _, _ = auth_service
    service.authenticate_user = AsyncMock(return_value=mock_user)
    service.rate_limit.check_failed_attempts = AsyncMock()
    service.rate_limit.clear_failed_attempts = AsyncMock()

    await service.login(UserLogin(email=mock_user.email, password="password123"))

    service.rate_limit.clear_failed_attempts.assert_called_once_with(mock_user.email)


@pytest.mark.asyncio
async def test_create_user(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test user creation."""
    service, mock_user_service, _, _ = auth_service
    user_data = UserCreate(email=mock_user.email, username=mock_user.username, password="password123")
    mock_user_service.create_user = AsyncMock(return_value=mock_user)

    created_user = await service.create_user(user_data)
    assert created_user.email == user_data.email
    assert created_user.username == user_data.username
    assert created_user.hashed_password != user_data.password  # Password should be hashed


def test_verify_token(auth_service):  # pylint: disable=redefined-outer-name
    """Test token verification."""
    service, _, _, _ = auth_service
    email = "test@example.com"
    token = jwt.encode(
        {"sub": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=30), "type": "access"}, str(JWT_SECRET_KEY), algorithm="HS256"
    )

    assert service.verify_token(token) == email

    # Test invalid token
    with pytest.raises(HTTPException):
        service.verify_token("invalid-token")


@pytest.mark.asyncio
async def test_login_invalid_credentials(auth_service):  # pylint: disable=redefined-outer-name
    """Test login with invalid credentials."""
    service, mock_user_service, _, _ = auth_service
    service.authenticate_user = AsyncMock(return_value=None)
    service.rate_limit.check_failed_attempts = AsyncMock()
    service.rate_limit.record_failed_login = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await service.login(UserLogin(email="test@example.com", password="wrong"))
    assert exc.value.status_code == 401
    service.rate_limit.record_failed_login.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_token_invalid(auth_service):  # pylint: disable=redefined-outer-name
    """Test refresh with invalid token."""
    service, _, _, _ = auth_service
    new_token = await service.refresh_access_token("invalid-token")
    assert new_token is None


def test_verify_token_expired(auth_service):  # pylint: disable=redefined-outer-name
    """Test verification of expired token."""
    service, _, _, _ = auth_service
    email = "test@example.com"
    token = jwt.encode(
        {"sub": email, "exp": datetime.now(timezone.utc) - timedelta(minutes=1), "type": "access"}, str(JWT_SECRET_KEY), algorithm="HS256"
    )
    with pytest.raises(HTTPException):
        service.verify_token(token)


@pytest.mark.asyncio
async def test_update_password_success(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test successful password update."""
    service, mock_user_service, _, _ = auth_service
    service.authenticate_user = AsyncMock(return_value=mock_user)
    mock_user_service.update_password = AsyncMock()

    result = await service.update_password(email="test@example.com", old_password="OldPass123", new_password="NewPass123")
    assert result is True
    mock_user_service.update_password.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_incorrect_old(auth_service):  # pylint: disable=redefined-outer-name
    """Test password update with incorrect old password."""
    service, mock_user_service, _, _ = auth_service
    service.authenticate_user = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.update_password(email="test@example.com", old_password="WrongPass", new_password="NewPass123")
    assert exc.value.status_code == 401
    assert "Current password is incorrect" in exc.value.detail


@pytest.mark.asyncio
async def test_update_password_weak_new(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test password update with weak new password."""
    service, mock_user_service, _, _ = auth_service
    service.authenticate_user = AsyncMock(return_value=mock_user)

    with pytest.raises(HTTPException) as exc:
        await service.update_password(email="test@example.com", old_password="OldPass123", new_password="weak")
    assert exc.value.status_code == 400
    assert "password is too weak" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_initiate_password_reset_success(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test successful password reset initiation."""
    service, mock_user_service, _, mock_email_service = auth_service
    mock_user_service.get_user = AsyncMock(return_value=mock_user)
    mock_email_service.send_reset_email = AsyncMock()

    await service.initiate_password_reset("test@example.com")

    # Verify email was sent
    mock_email_service.send_reset_email.assert_called_once()
    call_args = mock_email_service.send_reset_email.call_args[1]
    assert call_args["email"] == "test@example.com"
    assert call_args["username"] == mock_user.username
    assert isinstance(call_args["token"], str)


@pytest.mark.asyncio
async def test_initiate_password_reset_invalid_email(auth_service):  # pylint: disable=redefined-outer-name
    """Test password reset for a non-existent email.
    The service should not raise an error but return silently.
    """
    service, mock_user_service, _, mock_email_service = auth_service
    mock_user_service.get_user = AsyncMock(return_value=None)  # Simulate user not found
    mock_email_service.send_reset_email = AsyncMock()  # Ensure it starts fresh for this test

    # Call the method - it should not raise an exception
    await service.initiate_password_reset("nonexistent@example.com")

    # Verify user_service.get_user was called
    mock_user_service.get_user.assert_called_once_with("nonexistent@example.com")

    # Verify no email was sent
    mock_email_service.send_reset_email.assert_not_called()


@pytest.mark.asyncio
async def test_complete_password_reset_success(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test successful password reset completion."""
    # Mock user service to return a proper user object
    service, mock_user_service, _, mock_email_service = auth_service
    mock_user_service.get_user = AsyncMock(return_value=mock_user)
    mock_email_service.send_reset_email = AsyncMock()

    # Get valid reset token
    token = service._generate_reset_token("test@example.com")
    mock_user_service.update_password = AsyncMock()

    await service.complete_password_reset(token, "NewPass123")
    mock_user_service.update_password.assert_called_once()


@pytest.mark.asyncio
async def test_complete_password_reset_invalid_token(auth_service):  # pylint: disable=redefined-outer-name
    """Test password reset with invalid token."""
    service, _, _, _ = auth_service
    with pytest.raises(HTTPException) as exc:
        await service.complete_password_reset("invalid-token", "NewPass123")
    assert exc.value.status_code == 400
    assert "Invalid reset token" in exc.value.detail


@pytest.mark.asyncio
async def test_complete_password_reset_weak_password(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test password reset with weak new password."""
    # Mock user service to return a proper user object
    service, mock_user_service, _, mock_email_service = auth_service
    mock_user_service.get_user = AsyncMock(return_value=mock_user)
    mock_email_service.send_reset_email = AsyncMock()

    # Generate token directly
    token = service._generate_reset_token("test@example.com")

    with pytest.raises(HTTPException) as exc:
        await service.complete_password_reset(token, "weak")
    assert exc.value.status_code == 400
    assert "Password too weak" in exc.value.detail


@pytest.mark.asyncio
async def test_refresh_token_wrong_type(auth_service):  # pylint: disable=redefined-outer-name
    """Test refresh with access token instead of refresh token."""
    # Create an access token
    service, _, _, _ = auth_service
    token = jwt.encode(
        {
            "sub": "test@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "type": "access",  # Wrong token type
        },
        str(JWT_REFRESH_SECRET_KEY),
        algorithm="HS256",
    )
    assert await service.refresh_access_token(token) is None


@pytest.mark.asyncio
async def test_token_expiry_times(auth_service):  # pylint: disable=redefined-outer-name
    """Test token expiration times are set correctly."""
    service, _, _, _ = auth_service
    email = "test@example.com"
    access_token, refresh_token = await service.create_tokens(email)

    access_payload = jwt.decode(access_token, str(JWT_SECRET_KEY), algorithms=["HS256"])
    refresh_payload = jwt.decode(refresh_token, str(JWT_REFRESH_SECRET_KEY), algorithms=["HS256"])

    now = datetime.now(timezone.utc).timestamp()
    assert access_payload["exp"] - now <= 30 * 60  # 30 minutes
    assert refresh_payload["exp"] - now <= 7 * 24 * 60 * 60  # 7 days
