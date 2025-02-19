"""Authentication routes with security measures."""

from fastapi import APIRouter, HTTPException, status
from fastapi.security import HTTPBearer

from src.models.user import UserCreate, UserLogin
from src.services.auth_service import AuthService

router = APIRouter()
auth_service = AuthService()
security = HTTPBearer()


@router.post("/register")
async def register(user: UserCreate):
    """Register a new user with validation."""
    # Validate email format and password strength
    if not auth_service.is_valid_email(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

    if not auth_service.is_strong_password(user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too weak")

    if await auth_service.get_user(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user_in_db = await auth_service.create_user(user)
    token = auth_service.create_token(user_in_db.email)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login")
async def login(user: UserLogin):
    """Login with brute force protection."""
    # Check for too many failed attempts
    await auth_service.check_failed_attempts(user.email)

    user_in_db = await auth_service.authenticate_user(user.email, user.password)
    if not user_in_db:
        await auth_service.db.record_failed_login(user.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    # Reset failed attempts on successful login
    await auth_service.db.clear_failed_attempts(user.email)
    token = auth_service.create_token(user_in_db.email)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/refresh")
async def refresh_token(refresh_token: str):
    """Refresh access token."""
    new_token = await auth_service.refresh_access_token(refresh_token)
    if not new_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    return {"access_token": new_token, "token_type": "bearer"}
