"""Test the authentication API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import router
from src.models.user import Token

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.mark.asyncio
async def test_register_endpoint():
    """Test user registration endpoint."""
    with patch("src.api.auth.auth_service") as mock_auth:
        mock_auth.is_valid_email.return_value = True
        mock_auth.is_strong_password.return_value = True
        mock_auth.get_user = AsyncMock(return_value=None)
        mock_auth.create_user = AsyncMock()
        mock_auth.create_tokens = AsyncMock(return_value=("access", "refresh"))

        response = client.post("/register", json={"email": "test@example.com", "username": "testuser", "password": "Password123"})
        assert response.status_code == 200
        assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_endpoint():
    """Test login endpoint."""
    with patch("src.api.auth.auth_service") as mock_auth:
        mock_auth.login = AsyncMock(return_value=Token(access_token="access", refresh_token="refresh", token_type="bearer"))

        response = client.post("/login", json={"email": "test@example.com", "password": "Password123"})
        assert response.status_code == 200
        assert response.json()["token_type"] == "bearer"
