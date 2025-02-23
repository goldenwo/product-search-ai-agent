"""Test the AuthService class."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from fastapi import HTTPException

from src.models.user import UserCreate, UserInDB, UserLogin
from src.services.auth_service import AuthService
from src.utils.config import JWT_REFRESH_SECRET_KEY, JWT_SECRET_KEY


@pytest.fixture
def auth_service():
    """Create AuthService with mocked dependencies."""
    service = AuthService()
    service.user_service = Mock()
    service.rate_limit = Mock()
    return service


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
    plain_password = "password123"
    hashed = auth_service.get_password_hash(plain_password)
    assert auth_service.verify_password(plain_password, hashed)
    assert not auth_service.verify_password("wrongpass", hashed)


def test_email_validation(auth_service):  # pylint: disable=redefined-outer-name
    """Test email format validation."""
    assert auth_service.is_valid_email("test@example.com")
    assert not auth_service.is_valid_email("invalid-email")
    assert not auth_service.is_valid_email("@example.com")
    assert not auth_service.is_valid_email("test@.com")


def test_password_strength(auth_service):  # pylint: disable=redefined-outer-name
    """Test password strength requirements."""
    assert auth_service.is_strong_password("Password123")
    assert not auth_service.is_strong_password("password")  # No uppercase/numbers
    assert not auth_service.is_strong_password("12345678")  # No letters
    assert not auth_service.is_strong_password("Pass")  # Too short


@pytest.mark.asyncio
async def test_create_tokens(auth_service):  # pylint: disable=redefined-outer-name
    """Test JWT token creation."""
    email = "test@example.com"
    access_token, refresh_token = await auth_service.create_tokens(email)

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
    email = "test@example.com"
    refresh_token = jwt.encode(
        {"sub": email, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}, str(JWT_REFRESH_SECRET_KEY), algorithm="HS256"
    )

    new_token = await auth_service.refresh_access_token(refresh_token)
    assert new_token is not None

    # Verify new token
    payload = jwt.decode(new_token, str(JWT_SECRET_KEY), algorithms=["HS256"])
    assert payload["sub"] == email
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_login_success(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test successful login flow."""
    auth_service.authenticate_user = AsyncMock(return_value=mock_user)
    auth_service.rate_limit.check_failed_attempts = AsyncMock()
    auth_service.rate_limit.clear_failed_attempts = AsyncMock()

    login_data = UserLogin(email=mock_user.email, password="password123")
    token = await auth_service.login(login_data)

    assert token.access_token
    assert token.refresh_token
    assert token.token_type == "bearer"
    auth_service.rate_limit.clear_failed_attempts.assert_called_once()


@pytest.mark.asyncio
async def test_login_rate_limit(auth_service):  # pylint: disable=redefined-outer-name
    """Test login rate limiting with 30-minute lockout."""
    # Mock rate limit service to simulate max attempts reached
    auth_service.rate_limit.check_failed_attempts = AsyncMock(
        side_effect=HTTPException(status_code=429, detail="Too many failed attempts. Account locked for 30 minutes.")
    )
    auth_service.rate_limit.record_failed_login = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await auth_service.login(UserLogin(email="test@example.com", password="password123"))
    assert exc.value.status_code == 429
    assert "Account locked for 30 minutes" in exc.value.detail


@pytest.mark.asyncio
async def test_login_failure_increments_attempts(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test that failed login increments attempt counter."""
    auth_service.authenticate_user = AsyncMock(return_value=None)  # Auth fails
    auth_service.rate_limit.check_failed_attempts = AsyncMock()  # No rate limit yet
    auth_service.rate_limit.record_failed_login = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await auth_service.login(UserLogin(email="test@example.com", password="wrong"))

    assert exc.value.status_code == 401
    auth_service.rate_limit.record_failed_login.assert_called_once()


@pytest.mark.asyncio
async def test_login_success_clears_attempts(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test that successful login clears attempt counter."""
    auth_service.authenticate_user = AsyncMock(return_value=mock_user)
    auth_service.rate_limit.check_failed_attempts = AsyncMock()
    auth_service.rate_limit.clear_failed_attempts = AsyncMock()

    await auth_service.login(UserLogin(email=mock_user.email, password="password123"))

    auth_service.rate_limit.clear_failed_attempts.assert_called_once_with(mock_user.email)


@pytest.mark.asyncio
async def test_create_user(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test user creation."""
    user_data = UserCreate(email=mock_user.email, username=mock_user.username, password="password123")
    auth_service.user_service.create_user = AsyncMock(return_value=mock_user)

    created_user = await auth_service.create_user(user_data)
    assert created_user.email == user_data.email
    assert created_user.username == user_data.username
    assert created_user.hashed_password != user_data.password  # Password should be hashed


def test_verify_token(auth_service):  # pylint: disable=redefined-outer-name
    """Test token verification."""
    email = "test@example.com"
    token = jwt.encode(
        {"sub": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=30), "type": "access"}, str(JWT_SECRET_KEY), algorithm="HS256"
    )

    assert auth_service.verify_token(token) == email

    # Test invalid token
    with pytest.raises(HTTPException):
        auth_service.verify_token("invalid-token")


@pytest.mark.asyncio
async def test_login_invalid_credentials(auth_service):  # pylint: disable=redefined-outer-name
    """Test login with invalid credentials."""
    auth_service.authenticate_user = AsyncMock(return_value=None)
    auth_service.rate_limit.check_failed_attempts = AsyncMock()
    auth_service.rate_limit.record_failed_login = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await auth_service.login(UserLogin(email="test@example.com", password="wrong"))
    assert exc.value.status_code == 401
    auth_service.rate_limit.record_failed_login.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_token_invalid(auth_service):  # pylint: disable=redefined-outer-name
    """Test refresh with invalid token."""
    new_token = await auth_service.refresh_access_token("invalid-token")
    assert new_token is None


def test_verify_token_expired(auth_service):  # pylint: disable=redefined-outer-name
    """Test verification of expired token."""
    email = "test@example.com"
    token = jwt.encode(
        {"sub": email, "exp": datetime.now(timezone.utc) - timedelta(minutes=1), "type": "access"}, str(JWT_SECRET_KEY), algorithm="HS256"
    )
    with pytest.raises(HTTPException):
        auth_service.verify_token(token)


@pytest.mark.asyncio
async def test_update_password_success(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test successful password update."""
    auth_service.authenticate_user = AsyncMock(return_value=mock_user)
    auth_service.user_service.update_password = AsyncMock()

    result = await auth_service.update_password(email="test@example.com", old_password="OldPass123", new_password="NewPass123")
    assert result is True
    auth_service.user_service.update_password.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_incorrect_old(auth_service):  # pylint: disable=redefined-outer-name
    """Test password update with incorrect old password."""
    auth_service.authenticate_user = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await auth_service.update_password(email="test@example.com", old_password="WrongPass", new_password="NewPass123")
    assert exc.value.status_code == 401
    assert "Current password is incorrect" in exc.value.detail


@pytest.mark.asyncio
async def test_update_password_weak_new(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test password update with weak new password."""
    auth_service.authenticate_user = AsyncMock(return_value=mock_user)

    with pytest.raises(HTTPException) as exc:
        await auth_service.update_password(email="test@example.com", old_password="OldPass123", new_password="weak")
    assert exc.value.status_code == 400
    assert "password is too weak" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_initiate_password_reset_success(auth_service, mock_user):  # pylint: disable=redefined-outer-name
    """Test successful password reset initiation."""
    auth_service.user_service.get_user = AsyncMock(return_value=mock_user)

    reset_token = await auth_service.initiate_password_reset("test@example.com")
    assert isinstance(reset_token, str)
    # Verify token structure
    payload = jwt.decode(reset_token, str(JWT_SECRET_KEY), algorithms=["HS256"])
    assert payload["type"] == "reset"
    assert payload["sub"] == "test@example.com"


@pytest.mark.asyncio
async def test_initiate_password_reset_invalid_email(auth_service):  # pylint: disable=redefined-outer-name
    """Test password reset with invalid email."""
    auth_service.user_service.get_user = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await auth_service.initiate_password_reset("nonexistent@example.com")
    assert exc.value.status_code == 404
    assert "Email not found" in exc.value.detail


@pytest.mark.asyncio
async def test_complete_password_reset_success(auth_service):  # pylint: disable=redefined-outer-name
    """Test successful password reset completion."""
    # Get a valid reset token through the public method
    auth_service.user_service.get_user = AsyncMock(return_value=True)
    token = await auth_service.initiate_password_reset("test@example.com")
    auth_service.user_service.update_password = AsyncMock()

    await auth_service.complete_password_reset(token, "NewPass123")
    auth_service.user_service.update_password.assert_called_once()


@pytest.mark.asyncio
async def test_complete_password_reset_invalid_token(auth_service):  # pylint: disable=redefined-outer-name
    """Test password reset with invalid token."""
    with pytest.raises(HTTPException) as exc:
        await auth_service.complete_password_reset("invalid-token", "NewPass123")
    assert exc.value.status_code == 400
    assert "Invalid or expired reset token" in exc.value.detail


@pytest.mark.asyncio
async def test_complete_password_reset_weak_password(auth_service):  # pylint: disable=redefined-outer-name
    """Test password reset with weak new password."""
    # Get valid token through public method
    auth_service.user_service.get_user = AsyncMock(return_value=True)
    token = await auth_service.initiate_password_reset("test@example.com")

    with pytest.raises(HTTPException) as exc:
        await auth_service.complete_password_reset(token, "weak")
    assert exc.value.status_code == 400
    assert "Password too weak" in exc.value.detail


@pytest.mark.asyncio
async def test_refresh_token_wrong_type(auth_service):
    """Test refresh with access token instead of refresh token."""
    # Create an access token
    token = jwt.encode(
        {
            "sub": "test@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "type": "access",  # Wrong token type
        },
        str(JWT_REFRESH_SECRET_KEY),
        algorithm="HS256",
    )
    assert await auth_service.refresh_access_token(token) is None


@pytest.mark.asyncio
async def test_token_expiry_times(auth_service):
    """Test token expiration times are set correctly."""
    email = "test@example.com"
    access_token, refresh_token = await auth_service.create_tokens(email)

    access_payload = jwt.decode(access_token, str(JWT_SECRET_KEY), algorithms=["HS256"])
    refresh_payload = jwt.decode(refresh_token, str(JWT_REFRESH_SECRET_KEY), algorithms=["HS256"])

    now = datetime.now(timezone.utc).timestamp()
    assert access_payload["exp"] - now <= 30 * 60  # 30 minutes
    assert refresh_payload["exp"] - now <= 7 * 24 * 60 * 60  # 7 days
