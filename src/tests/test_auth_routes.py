"""Test the authentication API endpoints."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import AsyncClient
from httpx import Response as HttpxResponse
import pytest

from src.dependencies import get_auth_service  # To override this dependency
from src.models.user import Token, UserCreate, UserInDB  # For type hinting and mock return values
from src.services.auth_service import AuthService  # For spec in MagicMock


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
async def test_register_success(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test successful user registration."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    # Mock UserInDB that create_user would return
    mock_created_user = UserInDB(email="newuser@example.com", username="newbie", hashed_password="somehash", is_verified=False)
    mock_auth_service.create_user.return_value = mock_created_user

    user_data = {"email": "newuser@example.com", "username": "newbie", "password": "ValidPass123"}
    response: HttpxResponse = await client.post("/auth/register", json=user_data)

    assert response.status_code == 200  # Assuming 200 OK for now, could be 201
    mock_auth_service.is_valid_email.assert_called_once_with("newuser@example.com")
    mock_auth_service.is_strong_password.assert_called_once_with("ValidPass123")
    mock_auth_service.get_user.assert_called_once_with("newuser@example.com")  # Checks if user exists
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

    del app.dependency_overrides[get_auth_service]  # Cleanup


@pytest.mark.asyncio
async def test_register_email_exists(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test registration when email already exists."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    # Simulate user already exists
    mock_auth_service.get_user.return_value = UserInDB(email="existing@example.com", username="existinguser", hashed_password="hash")
    # is_valid_email and is_strong_password will use their fixture defaults (True)

    user_data = {"email": "existing@example.com", "username": "newuser", "password": "ValidPass123"}
    response: HttpxResponse = await client.post("/auth/register", json=user_data)

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

    mock_auth_service.is_valid_email.assert_called_once_with("existing@example.com")
    mock_auth_service.is_strong_password.assert_called_once_with("ValidPass123")
    mock_auth_service.get_user.assert_called_once_with("existing@example.com")
    mock_auth_service.create_user.assert_not_called()  # Should not be called if user exists

    del app.dependency_overrides[get_auth_service]


# --- Login Tests ---
@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test successful user login."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    # Configure login to succeed and return a Token object (or its constituent parts)
    mock_auth_service.login.return_value = Token(access_token="logged_in_access_token", refresh_token="logged_in_refresh_token", token_type="bearer")

    login_data = {"email": "test@example.com", "password": "password123"}
    response: HttpxResponse = await client.post("/auth/login", json=login_data)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["access_token"] == "logged_in_access_token"

    mock_auth_service.login.assert_called_once()
    # You can assert the UserLogin object passed to auth_service.login
    # called_arg = mock_auth_service.login.call_args[0][0]
    # assert isinstance(called_arg, UserLogin)
    # assert called_arg.email == login_data["email"]

    del app.dependency_overrides[get_auth_service]


# Add tests for login failure (wrong credentials, user locked out - requires mocking rate_limit interactions within AuthService mock)


# --- Refresh Token Tests ---
@pytest.mark.asyncio
async def test_refresh_token_success(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test successful token refresh."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.refresh_access_token.return_value = "new_refreshed_access_token"

    response: HttpxResponse = await client.post("/auth/refresh?token=a_valid_refresh_token")  # Added await

    assert response.status_code == 200
    mock_auth_service.refresh_access_token.assert_called_once_with("a_valid_refresh_token")
    response_data = response.json()
    assert response_data["access_token"] == "new_refreshed_access_token"

    del app.dependency_overrides[get_auth_service]


# Add tests for refresh token failure (invalid token)


# --- Password Reset Request Tests ---
@pytest.mark.asyncio
async def test_password_reset_request(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test password reset request."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    test_email = "user@example.com"
    response: HttpxResponse = await client.post(f"/auth/password/reset-request?email={test_email}")  # Added await

    assert response.status_code == 200
    mock_auth_service.initiate_password_reset.assert_called_once_with(test_email)
    assert response.json() == {"message": "If email exists, reset instructions have been sent"}

    del app.dependency_overrides[get_auth_service]


# --- Complete Password Reset Tests ---
@pytest.mark.asyncio
async def test_complete_password_reset_success(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test successful password reset completion."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.complete_password_reset.return_value = True

    reset_params = {"token": "valid_reset_token", "new_password": "NewStrongPassword123"}
    response: HttpxResponse = await client.post("/auth/password/reset", params=reset_params)  # Added await

    assert response.status_code == 200
    mock_auth_service.complete_password_reset.assert_called_once_with("valid_reset_token", "NewStrongPassword123")
    assert response.json() == {"message": "Password updated successfully"}

    del app.dependency_overrides[get_auth_service]


# --- Update Password Tests ---
@pytest.mark.asyncio
async def test_update_password_success(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test successful password update for an authenticated user."""

    original_app_state_auth_service = getattr(app.state, "auth_service", None)
    app.state.auth_service = mock_auth_service  # Ensure middleware uses this mock
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service  # For route DI

    headers = {"Authorization": "Bearer fake_access_token_for_update"}
    update_params = {"old_password": "OldPassword123", "new_password": "NewerStrongerPassword123"}

    decoded_token_payload = {"sub": "testuser@example.com", "type": "access", "jti": "a_valid_jti_for_this_test"}

    with patch("src.middleware.jwt.decode", return_value=decoded_token_payload) as mock_jwt_decode:
        mock_auth_service.is_jti_denylisted.return_value = False

        response: HttpxResponse = await client.post("/auth/password/update", params=update_params, headers=headers)

        assert response.status_code == 200

        mock_jwt_decode.assert_called_once_with(
            "fake_access_token_for_update",
            ANY,  # JWT_SECRET_KEY from config
            algorithms=[ANY],  # JWT_ALGORITHM from config
        )

        mock_auth_service.is_jti_denylisted.assert_called_once_with("a_valid_jti_for_this_test")
        mock_auth_service.update_password.assert_called_once_with("testuser@example.com", "OldPassword123", "NewerStrongerPassword123")
        assert response.json() == {"message": "Password updated successfully"}

    # Cleanup
    del app.dependency_overrides[get_auth_service]
    if original_app_state_auth_service:
        app.state.auth_service = original_app_state_auth_service
    elif hasattr(app.state, "auth_service"):
        delattr(app.state, "auth_service")


# --- Verify Email Tests ---
@pytest.mark.asyncio
async def test_verify_email_success(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test successful email verification."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    mock_auth_service.verify_email_token.return_value = True

    verification_token = "valid_verification_token"
    response: HttpxResponse = await client.get(f"/auth/verify-email?token={verification_token}")  # Added await

    assert response.status_code == 200
    mock_auth_service.verify_email_token.assert_called_once_with(verification_token)
    assert response.json() == {"message": "Email verified successfully. You can now log in."}

    del app.dependency_overrides[get_auth_service]


# --- Logout Tests ---
@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient, mock_auth_service: MagicMock, app: FastAPI):
    """Test successful logout."""
    original_app_state_auth_service = getattr(app.state, "auth_service", None)
    app.state.auth_service = mock_auth_service  # Ensure middleware uses this mock
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service  # For route DI

    headers = {"Authorization": "Bearer fake_access_token_to_logout"}

    # Mock the JWT decoding for the middleware
    decoded_token_payload = {"sub": "testuser@example.com", "type": "access", "jti": "a_valid_jti_for_logout"}

    with patch("src.middleware.jwt.decode", return_value=decoded_token_payload) as mock_jwt_decode:
        mock_auth_service.is_jti_denylisted.return_value = False  # Ensure this is set for the middleware check

        response: HttpxResponse = await client.post("/auth/logout", headers=headers)

        assert response.status_code == 200
        assert "Logout successful" in response.json()["message"]

        # Verify middleware interactions and route handler interactions with jwt.decode
        assert mock_jwt_decode.call_count == 2

        # Call 1: From AuthMiddleware
        middleware_call = mock_jwt_decode.call_args_list[0]
        assert middleware_call[0][0] == "fake_access_token_to_logout"
        assert middleware_call[0][1] == ANY  # JWT_SECRET_KEY
        assert middleware_call[1]["algorithms"] == [ANY]  # JWT_ALGORITHM
        assert "options" not in middleware_call[1]  # Middleware call does not set options={'verify_exp': False}

        # Call 2: From logout route handler in src/api/auth.py
        route_handler_call = mock_jwt_decode.call_args_list[1]
        assert route_handler_call[0][0] == "fake_access_token_to_logout"
        assert route_handler_call[0][1] == ANY  # JWT_SECRET_KEY
        assert route_handler_call[1]["algorithms"] == [ANY]  # JWT_ALGORITHM
        assert route_handler_call[1]["options"] == {"verify_exp": False}

        mock_auth_service.is_jti_denylisted.assert_called_once_with("a_valid_jti_for_logout")

        # Verify route handler interaction with add_jti_to_denylist
        mock_auth_service.add_jti_to_denylist.assert_called_once()
        assert mock_auth_service.add_jti_to_denylist.call_args[0][0] == "a_valid_jti_for_logout"

    # Cleanup
    del app.dependency_overrides[get_auth_service]
    if original_app_state_auth_service:
        app.state.auth_service = original_app_state_auth_service
    elif hasattr(app.state, "auth_service"):
        delattr(app.state, "auth_service")


# Remember to add tests for failure cases for each endpoint:
# - Invalid input data (e.g., bad email format for register)
# - Incorrect passwords/tokens
# - Service layer raising HTTPExceptions (e.g., user not found, token expired)
# - Rate limiting being hit (this is harder to test with unit-style endpoint tests
# might need integration tests or specific slowapi testing utilities)
