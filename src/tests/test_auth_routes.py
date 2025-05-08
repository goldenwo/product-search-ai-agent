"""Test the authentication API endpoints."""

from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

from fastapi import FastAPI, status
from fastapi.exceptions import HTTPException
from httpx import ASGITransport, AsyncClient
from httpx import Response as HttpxResponse

# Import jwt module for patch.object strategy
import jwt as jwt_module_for_patching
import pytest

# # Add this import for the minimal middleware
# from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
# from starlette.requests import Request as StarletteRequest # To avoid conflict with FastAPI's Request
# from starlette.responses import Response as StarletteResponse # To avoid conflict with FastAPI's Response
from src.dependencies import get_auth_service  # To override this dependency
from src.models.user import (
    Token,
    UserCreate,
    UserInDB,
    UserLogin,  # Added UserLogin import
)
from src.services.auth_service import AuthService  # For spec in MagicMock
from src.services.email_service import EmailService  # For spec in MagicMock

# # Define a minimal pass-through middleware for testing
# class MinimalNoOpMiddleware(BaseHTTPMiddleware):
#     async def dispatch(self, request: StarletteRequest, call_next: RequestResponseEndpoint) -> StarletteResponse:
#         print(f"MinimalNoOpMiddleware: dispatch() called for {request.url.path}") # Use print for immediate visibility
#         response = await call_next(request)
#         return response


@pytest.fixture
def mock_auth_service(mocker):
    """Provides a fresh MagicMock for AuthService for each test that needs it."""
    # Create a MagicMock instance that mimics AuthService
    service = mocker.MagicMock(spec=AuthService)

    # Pre-configure common success cases for methods directly used by routes
    # These can be overridden in individual tests if needed for failure cases
    service.is_valid_email.return_value = True
    service.is_strong_password.return_value = True
    service.get_user.return_value = None  # Default: user doesn't exist

    # Mock async methods using AsyncMock if they are directly awaited
    # For methods that return values needed by other logic in the route:
    service.create_user = AsyncMock()  # Will be configured in tests needing it
    service.create_tokens = AsyncMock(return_value=("test_access_token", "test_refresh_token"))
    service.login = AsyncMock()  # Will be configured in login tests
    service.refresh_access_token = AsyncMock()
    service.update_password = AsyncMock()
    service.initiate_password_reset = AsyncMock()
    service.complete_password_reset = AsyncMock()
    service.verify_email_token = AsyncMock()
    service.verify_token = MagicMock(return_value="testuser@example.com")  # For middleware mocking if needed directly
    service.add_jti_to_denylist = AsyncMock()
    service.is_jti_denylisted = AsyncMock(return_value=False)

    return service


# --- Registration Tests ---
@pytest.mark.asyncio
async def test_register_success(mock_auth_service: MagicMock, app: FastAPI):
    """Test successful user registration."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_created_user = UserInDB(email="newuser@example.com", username="newbie", hashed_password="somehash", is_verified=False)
    mock_auth_service.create_user.return_value = mock_created_user

    user_data = {"email": "newuser@example.com", "username": "newbie", "password": "ValidPass123"}

    # Manually create client within test
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.post("/auth/register", json=user_data)

        assert response.status_code == 200
        mock_auth_service.is_valid_email.assert_called_once_with("newuser@example.com")
        mock_auth_service.is_strong_password.assert_called_once_with("ValidPass123")
        mock_auth_service.get_user.assert_called_once_with("newuser@example.com")
        mock_auth_service.create_user.assert_called_once()
        called_arg = mock_auth_service.create_user.call_args[0][0]
        assert isinstance(called_arg, UserCreate)
        assert called_arg.email == user_data["email"]
        assert called_arg.username == user_data["username"]
        assert called_arg.password == user_data["password"]
        mock_auth_service.create_tokens.assert_called_once_with(mock_created_user.email)

        response_data = response.json()
        assert response_data["access_token"] == "test_access_token"
        assert response_data["refresh_token"] == "test_refresh_token"

    del app.dependency_overrides[get_auth_service]


@pytest.mark.asyncio
async def test_register_email_exists(mock_auth_service: MagicMock, app: FastAPI):
    """Test registration when email already exists."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.get_user.return_value = UserInDB(email="existing@example.com", username="existinguser", hashed_password="hash")

    user_data = {"email": "existing@example.com", "username": "newuser", "password": "ValidPass123"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.post("/auth/register", json=user_data)

        assert response.status_code == 400
        assert response.json()["detail"] == "Email already registered"
        mock_auth_service.is_valid_email.assert_called_once_with("existing@example.com")
        mock_auth_service.is_strong_password.assert_called_once_with("ValidPass123")
        mock_auth_service.get_user.assert_called_once_with("existing@example.com")
        mock_auth_service.create_user.assert_not_called()

    del app.dependency_overrides[get_auth_service]


# --- Login Tests ---
@pytest.mark.asyncio
async def test_login_success(mock_auth_service: MagicMock, app: FastAPI):
    """Test successful user login."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.login.return_value = Token(access_token="logged_in_access_token", refresh_token="logged_in_refresh_token", token_type="bearer")

    login_data = {"email": "test@example.com", "password": "password123"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.post("/auth/login", json=login_data)

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["access_token"] == "logged_in_access_token"
        mock_auth_service.login.assert_called_once()

    del app.dependency_overrides[get_auth_service]


@pytest.mark.asyncio
async def test_login_unverified_user(mock_auth_service: MagicMock, app: FastAPI):
    """Test login failure when user email is not verified."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    # Simulate AuthService.login raising the 403 Forbidden due to unverified email
    mock_auth_service.login = AsyncMock(
        side_effect=HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox for a verification link.",
        )
    )

    login_data = {"email": "unverified@example.com", "password": "password123"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.post("/auth/login", json=login_data)

        assert response.status_code == 403
        assert "Email not verified" in response.json()["detail"]
        mock_auth_service.login.assert_called_once_with(UserLogin(**login_data))  # Ensure service method was called

    del app.dependency_overrides[get_auth_service]


# --- Refresh Token Tests ---
@pytest.mark.asyncio
async def test_refresh_token_success(mock_auth_service: MagicMock, app: FastAPI):
    """Test successful token refresh."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.refresh_access_token.return_value = "new_refreshed_access_token"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.post("/auth/refresh?token=a_valid_refresh_token")

        assert response.status_code == 200
        mock_auth_service.refresh_access_token.assert_called_once_with("a_valid_refresh_token")
        response_data = response.json()
        assert response_data["access_token"] == "new_refreshed_access_token"

    del app.dependency_overrides[get_auth_service]


# Add tests for refresh token failure (invalid token)


# --- Password Reset Request Tests ---
@pytest.mark.asyncio
async def test_password_reset_request(mock_auth_service: MagicMock, app: FastAPI):
    """Test password reset request."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    test_email = "user@example.com"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.post(f"/auth/password/reset-request?email={test_email}")

        assert response.status_code == 200
        mock_auth_service.initiate_password_reset.assert_called_once_with(test_email)
        assert response.json() == {"message": "If email exists, reset instructions have been sent"}

    del app.dependency_overrides[get_auth_service]


# --- Complete Password Reset Tests ---
@pytest.mark.asyncio
async def test_complete_password_reset_success(mock_auth_service: MagicMock, app: FastAPI):
    """Test successful password reset completion."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.complete_password_reset.return_value = True

    reset_params = {"token": "valid_reset_token", "new_password": "NewStrongPassword123"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.post("/auth/password/reset", params=reset_params)

        assert response.status_code == 200
        mock_auth_service.complete_password_reset.assert_called_once_with("valid_reset_token", "NewStrongPassword123")
        assert response.json() == {"message": "Password updated successfully"}

    del app.dependency_overrides[get_auth_service]


# --- Update Password Tests ---
@pytest.mark.asyncio
async def test_update_password_success(mock_auth_service: MagicMock, app: FastAPI):
    """Test successful password update for an authenticated user."""

    # Explicitly set the app.state.auth_service for the middleware FOR THIS TEST
    # Overrides the one set by _setup_app_state fixture for this test's duration
    original_state_auth_service = getattr(app.state, "auth_service", None)
    app.state.auth_service = mock_auth_service

    # Also override the dependency for the route handler
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    headers = {"Authorization": "Bearer fake_access_token_for_update"}
    update_params = {"old_password": "OldPassword123", "new_password": "NewerStrongerPassword123"}
    decoded_token_payload = {"sub": "testuser@example.com", "type": "access", "jti": "a_valid_jti_for_this_test"}

    # Configure the single mock instance used by both middleware and route
    mock_auth_service.reset_mock()
    mock_auth_service.update_password = AsyncMock(return_value=True)
    mock_user = UserInDB(email="testuser@example.com", username="tester", hashed_password="$2b$12$dummyhashforvaliduser", is_verified=True)
    mock_auth_service.authenticate_user = AsyncMock(return_value=mock_user)
    mock_auth_service.get_user = AsyncMock(return_value=mock_user)
    mock_auth_service.verify_password = MagicMock(return_value=True)
    mock_auth_service.is_strong_password = MagicMock(return_value=True)
    mock_auth_service.email_service = MagicMock(spec=EmailService)
    mock_auth_service.email_service.send_password_change_notification = AsyncMock()
    # Crucially, ensure is_jti_denylisted is configured on this specific mock
    mock_auth_service.is_jti_denylisted = AsyncMock(return_value=False)

    try:
        with patch("src.middleware.jwt.decode", return_value=decoded_token_payload):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response: HttpxResponse = await client.post("/auth/password/update", params=update_params, headers=headers)

                assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. Response: {response.text}"
                assert response.json() == {"message": "Password updated successfully"}
                mock_auth_service.update_password.assert_called_once_with("testuser@example.com", "OldPassword123", "NewerStrongerPassword123")
                # Check middleware interaction
                mock_auth_service.is_jti_denylisted.assert_called_once_with("a_valid_jti_for_this_test")

    finally:
        # Cleanup overrides
        del app.dependency_overrides[get_auth_service]
        # Restore original state if it existed, otherwise remove
        if original_state_auth_service:
            app.state.auth_service = original_state_auth_service
        elif hasattr(app.state, "auth_service"):
            delattr(app.state, "auth_service")


# --- Verify Email Tests ---
@pytest.mark.asyncio
async def test_verify_email_success(mock_auth_service: MagicMock, app: FastAPI):
    """Test successful email verification."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.verify_email_token.return_value = True

    verification_token = "valid_verification_token"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.get(f"/auth/verify-email?token={verification_token}")

        assert response.status_code == 200
        mock_auth_service.verify_email_token.assert_called_once_with(verification_token)
        assert response.json() == {"message": "Email verified successfully. You can now log in."}

    del app.dependency_overrides[get_auth_service]


@pytest.mark.asyncio
async def test_verify_email_invalid_token(mock_auth_service: MagicMock, app: FastAPI):
    """Test email verification with an invalid or expired token."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    # Simulate AuthService.verify_email_token raising 400 for an invalid token
    mock_auth_service.verify_email_token = AsyncMock(
        side_effect=HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )
    )

    invalid_token = "this_token_is_not_valid"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response: HttpxResponse = await client.get(f"/auth/verify-email?token={invalid_token}")

        assert response.status_code == 400
        assert "Invalid or expired" in response.json()["detail"]
        mock_auth_service.verify_email_token.assert_called_once_with(invalid_token)

    del app.dependency_overrides[get_auth_service]


# --- Logout Tests ---
@pytest.mark.asyncio
async def test_logout_success(mock_auth_service: MagicMock, app: FastAPI):
    """Test successful logout."""
    # Explicitly set the app.state.auth_service for the middleware FOR THIS TEST
    original_state_auth_service = getattr(app.state, "auth_service", None)
    app.state.auth_service = mock_auth_service

    # Also override the dependency for the route handler
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    headers = {"Authorization": "Bearer fake_access_token_to_logout"}
    # Add 'exp' field to the payload for the middleware patch
    future_exp = datetime.now(timezone.utc) + timedelta(minutes=15)
    decoded_token_payload = {"sub": "testuser@example.com", "type": "access", "jti": "a_valid_jti_for_logout", "exp": int(future_exp.timestamp())}

    # Configure the mock_auth_service (used by both middleware and route handler via app.state and dependency override)
    mock_auth_service.reset_mock()  # Reset from any previous test usage if instance is reused by parametrize later
    mock_auth_service.is_jti_denylisted = AsyncMock(return_value=False)
    mock_auth_service.add_jti_to_denylist = AsyncMock(return_value=None)

    try:
        # Patch only the middleware's jwt.decode and JWT_SECRET_KEY
        with (
            patch.object(jwt_module_for_patching, "decode", return_value=decoded_token_payload) as mock_jwt_decode,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response: HttpxResponse = await client.post("/auth/logout", headers=headers)

                assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. Response: {response.text}"
                assert "Logout successful" in response.json()["message"]

                # Assert that the single mock was called ONCE (only by middleware)
                assert mock_jwt_decode.call_count == 1
                call_args = mock_jwt_decode.call_args
                assert call_args.args[0] == "fake_access_token_to_logout"
                assert call_args.kwargs["algorithms"] == [ANY]
                assert "options" not in call_args.kwargs  # Middleware call has no options

                # Assertions for middleware/service interactions
                mock_auth_service.is_jti_denylisted.assert_called_once_with("a_valid_jti_for_logout")  # Middleware check
                mock_auth_service.add_jti_to_denylist.assert_called_once_with(
                    "a_valid_jti_for_logout", ANY
                )  # Denylist TTL (Called by route handler using state)

    finally:
        # Cleanup overrides
        del app.dependency_overrides[get_auth_service]
        # Restore original state if it existed, otherwise remove
        if original_state_auth_service:
            app.state.auth_service = original_state_auth_service
        elif hasattr(app.state, "auth_service"):
            delattr(app.state, "auth_service")


# Remember to add tests for failure cases for each endpoint:
# - Invalid input data (e.g., bad email format for register)
# - Incorrect passwords/tokens
# - Service layer raising HTTPExceptions (e.g., user not found, token expired)
# - Rate limiting being hit (this is harder to test with unit-style endpoint tests
# might need integration tests or specific slowapi testing utilities)
