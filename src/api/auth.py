"""Authentication routes with security measures and rate limiting."""

from fastapi import APIRouter, HTTPException, status
from fastapi.security import HTTPBearer

from src.models.user import Token, UserCreate, UserLogin
from src.services.auth_service import AuthService

router = APIRouter()
auth_service = AuthService()
security = HTTPBearer()


@router.post("/register")
async def register(user: UserCreate):
    """
    Register a new user with validation.

    Args:
        user: User registration data

    Returns:
        Token: Access and refresh tokens

    Raises:
        HTTPException: If email format is invalid, password is weak, or email exists
    """
    # Validate email format and password strength
    if not auth_service.is_valid_email(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

    if not auth_service.is_strong_password(user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too weak")

    if await auth_service.get_user(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user_in_db = await auth_service.create_user(user)
    access_token, refresh_token = await auth_service.create_tokens(user_in_db.email)
    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post("/login")
async def login(user: UserLogin):
    """
    Login with brute force protection.

    Args:
        user: Login credentials

    Returns:
        Token: Access and refresh tokens

    Raises:
        HTTPException: If credentials are invalid or too many failed attempts
    """
    return await auth_service.login(user)  # Use the new login method


@router.post("/refresh")
async def refresh_token_handler(token: str):
    """
    Refresh access token using refresh token.

    Args:
        token: Refresh token

    Returns:
        dict: New access token

    Raises:
        HTTPException: If refresh token is invalid
    """
    new_token = await auth_service.refresh_access_token(token)
    if not new_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    return {"access_token": new_token, "token_type": "bearer"}
