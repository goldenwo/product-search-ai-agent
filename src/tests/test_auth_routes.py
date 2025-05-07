"""Test the authentication API endpoints."""

from typing import Iterator
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
import pytest

from src.dependencies import get_auth_service  # To override this dependency
from src.main import app  # Your FastAPI application instance
from src.models.user import Token, UserInDB, UserLogin  # For type hinting and mock return values
from src.services.auth_service import AuthService  # For spec in MagicMock


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provides a TestClient instance for making API requests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """Provides a mock AuthService instance."""
    mock = MagicMock(spec=AuthService)  # Use spec for better type checking on the mock

    # Configure default return values for common async methods
    # These can be overridden per test if needed
    mock.create_user = AsyncMock()
    mock.create_tokens = AsyncMock(return_value=("test_access_token", "test_refresh_token"))
    mock.login = AsyncMock(return_value=Token(access_token="login_access_token", refresh_token="login_refresh_token", token_type="bearer"))
    mock.refresh_access_token = AsyncMock(return_value="new_refreshed_access_token")
    mock.initiate_password_reset = AsyncMock()
    mock.complete_password_reset = AsyncMock(return_value=True)
    mock.verify_token = MagicMock(return_value="testuser@example.com")  # verify_token is synchronous
    mock.update_password = AsyncMock(return_value=True)
    mock.verify_email_token = AsyncMock(return_value=True)
    # Add other methods as needed by your routes
    return mock


# --- Registration Tests ---
@pytest.mark.asyncio
async def test_register_success(client: TestClient, mock_auth_service: MagicMock):
    """Test successful user registration."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    # Mock UserInDB that create_user would return
    mock_created_user = UserInDB(email="newuser@example.com", username="newbie", hashed_password="somehash", is_verified=False)
    mock_auth_service.create_user.return_value = mock_created_user

    user_data = {"email": "newuser@example.com", "username": "newbie", "password": "ValidPass123"}
    response = client.post("/auth/register", json=user_data)

    assert response.status_code == 200  # Assuming 200 OK for now, could be 201
    mock_auth_service.is_valid_email.assert_called_once_with("newuser@example.com")
    mock_auth_service.is_strong_password.assert_called_once_with("ValidPass123")
    mock_auth_service.get_user.assert_called_once_with("newuser@example.com")  # Checks if user exists
    mock_auth_service.create_user.assert_called_once()
    mock_auth_service.create_tokens.assert_called_once_with(mock_created_user.email)

    response_data = response.json()
    assert response_data["access_token"] == "test_access_token"
    assert response_data["refresh_token"] == "test_refresh_token"

    del app.dependency_overrides[get_auth_service]  # Cleanup


# Add tests for registration failure (invalid email, weak password, email exists) by configuring mock side_effects


# --- Login Tests ---
@pytest.mark.asyncio
async def test_login_success(client: TestClient, mock_auth_service: MagicMock):
    """Test successful user login."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    login_data = {"email": "test@example.com", "password": "ValidPass123"}
    response = client.post("/auth/login", json=login_data)

    assert response.status_code == 200
    # The login method in AuthService is called directly by the route
    mock_auth_service.login.assert_called_once_with(UserLogin(**login_data))
    response_data = response.json()
    assert response_data["access_token"] == "login_access_token"

    del app.dependency_overrides[get_auth_service]


# Add tests for login failure (wrong credentials, user locked out - requires mocking rate_limit interactions within AuthService mock)


# --- Refresh Token Tests ---
@pytest.mark.asyncio
async def test_refresh_token_success(client: TestClient, mock_auth_service: MagicMock):
    """Test successful token refresh."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    response = client.post("/auth/refresh?token=a_valid_refresh_token")  # Pass token as query param as per current route

    assert response.status_code == 200
    mock_auth_service.refresh_access_token.assert_called_once_with("a_valid_refresh_token")
    response_data = response.json()
    assert response_data["access_token"] == "new_refreshed_access_token"

    del app.dependency_overrides[get_auth_service]


# Add tests for refresh token failure (invalid token)


# --- Password Reset Request Tests ---
@pytest.mark.asyncio
async def test_password_reset_request(client: TestClient, mock_auth_service: MagicMock):
    """Test password reset request."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    test_email = "user@example.com"
    response = client.post(f"/auth/password/reset-request?email={test_email}")

    assert response.status_code == 200
    mock_auth_service.initiate_password_reset.assert_called_once_with(test_email)
    assert response.json() == {"message": "If email exists, reset instructions have been sent"}

    del app.dependency_overrides[get_auth_service]


# --- Complete Password Reset Tests ---
@pytest.mark.asyncio
async def test_complete_password_reset_success(client: TestClient, mock_auth_service: MagicMock):
    """Test successful password reset completion."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    reset_data = {"token": "valid_reset_token", "new_password": "NewStrongPassword123"}
    response = client.post("/auth/password/reset", params=reset_data)  # Params for GET, use json for POST if body
    # Current /password/reset takes token and new_password as query/form params, not JSON body
    # Let's assume they are query params for this test, matching the API definition implicitly

    assert response.status_code == 200
    mock_auth_service.complete_password_reset.assert_called_once_with("valid_reset_token", "NewStrongPassword123")
    assert response.json() == {"message": "Password updated successfully"}

    del app.dependency_overrides[get_auth_service]


# --- Update Password Tests ---
@pytest.mark.asyncio
async def test_update_password_success(client: TestClient, mock_auth_service: MagicMock):
    """Test successful password update for an authenticated user."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    # For authenticated routes, TestClient needs to send the Authorization header
    headers = {"Authorization": "Bearer fake_access_token"}
    update_data = {"old_password": "OldPassword123", "new_password": "NewerStrongerPassword123"}
    # The route takes these as query params, not JSON body
    response = client.post("/auth/password/update", params=update_data, headers=headers)

    assert response.status_code == 200
    mock_auth_service.verify_token.assert_called_once_with("fake_access_token")
    mock_auth_service.update_password.assert_called_once_with("testuser@example.com", "OldPassword123", "NewerStrongerPassword123")
    assert response.json() == {"message": "Password updated successfully"}

    del app.dependency_overrides[get_auth_service]


# --- Verify Email Tests ---
@pytest.mark.asyncio
async def test_verify_email_success(client: TestClient, mock_auth_service: MagicMock):
    """Test successful email verification."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    verification_token = "valid_verification_token"
    response = client.get(f"/auth/verify-email?token={verification_token}")

    assert response.status_code == 200
    mock_auth_service.verify_email_token.assert_called_once_with(verification_token)
    assert response.json() == {"message": "Email verified successfully. You can now log in."}

    del app.dependency_overrides[get_auth_service]


# --- Logout Tests ---
@pytest.mark.asyncio
async def test_logout_success(client: TestClient, mock_auth_service: MagicMock):
    """Test successful logout."""
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    headers = {"Authorization": "Bearer fake_access_token_to_logout"}
    # Mocking the decode part inside the logout route for simplicity here,
    # or ensure mock_auth_service.add_jti_to_denylist is called as expected.
    # For this test, we mostly care that the endpoint calls the service method.
    # The actual JTI denylisting logic is tested in AuthService tests.

    response = client.post("/auth/logout", headers=headers)

    assert response.status_code == 200
    # In a real test, you might want to assert that add_jti_to_denylist was called with correct JTI
    # This would require your mock_auth_service.add_jti_to_denylist to be an AsyncMock
    # and then inspecting its call_args, or having the logout route return something based on it.
    # For now, we check that a success-like message is returned.
    assert "Logout successful" in response.json()["message"]

    del app.dependency_overrides[get_auth_service]


# Remember to add tests for failure cases for each endpoint:
# - Invalid input data (e.g., bad email format for register)
# - Incorrect passwords/tokens
# - Service layer raising HTTPExceptions (e.g., user not found, token expired)
# - Rate limiting being hit (this is harder to test with unit-style endpoint tests
# might need integration tests or specific slowapi testing utilities)
