"""Authentication service for user management and token handling."""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer
from passlib.hash import bcrypt

from src.models.user import UserCreate, UserInDB
from src.services.database_service import DatabaseService
from src.utils.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_SECRET_KEY

security = HTTPBearer()


class AuthService:
    """Handles user authentication and token management."""

    def __init__(self):
        self.db = DatabaseService()

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Generate password hash."""
        return bcrypt.hash(password)

    def is_valid_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        return bool(re.match(pattern, email))

    def is_strong_password(self, password: str) -> bool:
        """Check password strength."""
        if len(password) < 8:
            return False
        if not re.search(r"[A-Z]", password):
            return False
        if not re.search(r"[a-z]", password):
            return False
        if not re.search(r"\d", password):
            return False
        return True

    async def get_user(self, email: str) -> Optional[UserInDB]:
        """Get user from database."""
        user_dict = await self.db.get_user(email)
        if user_dict:
            return UserInDB(**user_dict)
        return None

    async def authenticate_user(self, email: str, password: str) -> Optional[UserInDB]:
        """Authenticate user credentials."""
        user = await self.get_user(email)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user

    async def create_user(self, user: UserCreate) -> UserInDB:
        """Create new user in database."""
        hashed_password = self.get_password_hash(user.password)
        user_in_db = UserInDB(email=user.email, username=user.username, hashed_password=hashed_password)
        await self.db.create_user(user_in_db.model_dump())
        return user_in_db

    def create_token(self, email: str) -> str:
        """Create JWT access token."""
        if not JWT_SECRET_KEY:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWT secret key not configured")

        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {"sub": email, "exp": expire}
        return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm="HS256")

    def verify_token(self, token: str) -> str:
        """Verify JWT token and return user email."""
        try:
            payload = jwt.decode(token, str(JWT_SECRET_KEY), algorithms=["HS256"])
            email = str(payload.get("sub"))
            if not email:
                raise HTTPException(401, "Invalid token")
            return email
        except jwt.InvalidTokenError as exc:
            raise HTTPException(401, "Invalid token") from exc

    async def check_failed_attempts(self, email: str) -> None:
        """Check for too many failed login attempts."""
        attempts = await self.db.get_failed_attempts(email)
        if attempts >= 5:  # Max 5 attempts
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts. Try again later.")

    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Create new access token from refresh token."""
        try:
            payload = jwt.decode(refresh_token, str(JWT_SECRET_KEY), algorithms=["HS256"])
            email = str(payload.get("sub"))
            return self.create_token(email) if email else None
        except jwt.InvalidTokenError:
            return None
