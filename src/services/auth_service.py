"""Authentication service for JWT token management and user validation."""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer
from passlib.hash import bcrypt

from src.models.user import Token, UserCreate, UserInDB, UserLogin
from src.services.rate_limit_service import RateLimitService
from src.services.user_service import UserService
from src.utils.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_REFRESH_SECRET_KEY,
    JWT_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

security = HTTPBearer()


class AuthService:
    """
    Handles user authentication, token management, and security measures.

    Attributes:
        user_service: Service for user database operations
        rate_limit: Service for rate limiting
    """

    def __init__(self):
        self.user_service = UserService()
        self.rate_limit = RateLimitService()

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash using bcrypt.

        Args:
            plain_password: Plain text password
            hashed_password: Bcrypt hashed password

        Returns:
            bool: True if password matches hash
        """
        return bcrypt.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """
        Generate bcrypt hash of password.

        Args:
            password: Plain text password

        Returns:
            str: Bcrypt hashed password
        """
        return bcrypt.hash(password)

    def is_valid_email(self, email: str) -> bool:
        """
        Validate email format using regex.

        Args:
            email: Email address to validate

        Returns:
            bool: True if email format is valid
        """
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        return bool(re.match(pattern, email))

    def is_strong_password(self, password: str) -> bool:
        """
        Check password meets strength requirements.

        Password must:
        - Be at least 8 characters
        - Contain uppercase letter
        - Contain lowercase letter
        - Contain number

        Args:
            password: Password to check

        Returns:
            bool: True if password meets requirements
        """
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
        """
        Get user from database by email.

        Args:
            email: User's email address

        Returns:
            Optional[UserInDB]: User data if found, None otherwise
        """
        return await self.user_service.get_user(email)

    async def authenticate_user(self, email: str, password: str) -> Optional[UserInDB]:
        """
        Authenticate user with email and password.

        Args:
            email: User's email address
            password: Plain text password

        Returns:
            Optional[UserInDB]: User data if authenticated, None otherwise
        """
        user = await self.get_user(email)
        if not user or not self.verify_password(password, user.hashed_password):
            return None
        return user

    async def create_user(self, user: UserCreate) -> UserInDB:
        """
        Create new user with hashed password.

        Args:
            user: User creation data with plain password

        Returns:
            UserInDB: Created user data with hashed password
        """
        hashed_password = self.get_password_hash(user.password)
        return await self.user_service.create_user(user, hashed_password)

    async def create_tokens(self, email: str) -> Tuple[str, str]:
        """
        Create JWT access and refresh tokens.

        Args:
            email: User's email for token subject

        Returns:
            Tuple[str, str]: (access_token, refresh_token)

        Raises:
            HTTPException: If JWT configuration is missing
        """
        if not JWT_SECRET_KEY or not JWT_REFRESH_SECRET_KEY:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWT configuration missing")

        access_expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = jwt.encode({"sub": email, "exp": access_expire, "type": "access"}, str(JWT_SECRET_KEY), algorithm="HS256")

        refresh_expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_token = jwt.encode({"sub": email, "exp": refresh_expire, "type": "refresh"}, str(JWT_REFRESH_SECRET_KEY), algorithm="HS256")

        return access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Create new access token from refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            Optional[str]: New access token if refresh token valid, None otherwise
        """
        try:
            payload = jwt.decode(refresh_token, str(JWT_REFRESH_SECRET_KEY), algorithms=["HS256"])
            email = str(payload.get("sub"))
            token_type = str(payload.get("type"))

            if not email or token_type != "refresh":
                return None

            access_expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            return jwt.encode({"sub": email, "exp": access_expire, "type": "access"}, str(JWT_SECRET_KEY), algorithm="HS256")

        except jwt.InvalidTokenError:
            return None

    def verify_token(self, token: str) -> str:
        """
        Verify JWT token and extract user email.

        Args:
            token: JWT token to verify

        Returns:
            str: User's email from token

        Raises:
            HTTPException: If token is invalid
        """
        try:
            payload = jwt.decode(token, str(JWT_SECRET_KEY), algorithms=["HS256"])
            email = str(payload.get("sub"))
            if not email:
                raise HTTPException(401, "Invalid token")
            return email
        except jwt.InvalidTokenError as exc:
            raise HTTPException(401, "Invalid token") from exc

    async def check_failed_attempts(self, email: str) -> None:
        """
        Check if user has exceeded failed login attempts.

        Args:
            email: User's email address

        Raises:
            HTTPException: If too many failed attempts (rate limited)
        """
        attempts = await self.rate_limit.get_failed_attempts(email)
        if attempts >= 5:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts. Try again later.")

    async def login(self, user: UserLogin) -> Token:
        """
        Handle complete login flow with rate limiting.

        Args:
            user: Login credentials

        Returns:
            Token: Access and refresh tokens

        Raises:
            HTTPException: If credentials invalid or rate limited
        """
        await self.rate_limit.get_failed_attempts(user.email)

        user_db = await self.authenticate_user(user.email, user.password)
        if not user_db:
            await self.rate_limit.record_failed_login(user.email)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

        await self.rate_limit.clear_failed_attempts(user.email)
        access_token, refresh_token = await self.create_tokens(user_db.email)

        return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")
