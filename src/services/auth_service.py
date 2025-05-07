"""Authentication service for JWT token management and user validation."""

from datetime import datetime, timedelta, timezone
import re
import secrets
from typing import Optional, Tuple
import uuid

from fastapi import HTTPException, status
import jwt
from passlib.hash import bcrypt

from src.models.user import Token, UserCreate, UserInDB, UserLogin
from src.services.email_service import EmailService
from src.services.rate_limit_service import RateLimitService
from src.services.redis_service import RedisService
from src.services.user_service import UserService
from src.utils import logger
from src.utils.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_REFRESH_SECRET_KEY,
    JWT_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
    VERIFICATION_TOKEN_EXPIRE_HOURS,
)


class AuthService:
    """
    Handles user authentication, token management, and security measures.

    Attributes:
        user_service: Service for user database operations
        rate_limit: Service for rate limiting
        email_service: Service for email operations
        redis_service: Service for Redis operations
    """

    def __init__(self, redis_service: RedisService, user_service: UserService, email_service: EmailService):
        self.user_service = user_service
        self.rate_limit = RateLimitService(redis_client=redis_service.redis)
        self.email_service = email_service
        self.redis_service = redis_service
        self.password_reset_expiry = 3600  # 1 hour

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
            logger.warning("Authentication failed for email: %s", email)
            return None

        # Check if user is verified.
        # UserInDB model now has is_verified, and UserService.get_user populates it.
        if not user.is_verified:
            logger.warning("Login attempt by unverified user: %s", email)
            # Option 1: Deny login completely
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified. Please check your inbox for a verification link.")
            # Option 2: Allow login but with a special status/limited access (more complex)
            # For now, let's deny login.

        logger.info("User authenticated successfully: %s", email)
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
        created_user = await self.user_service.create_user(user, hashed_password)
        logger.info("User created successfully: %s", created_user.email)
        # After user is created, generate and send verification email
        try:
            verification_token = self._generate_alnum_token()  # More secure than just JWT for this
            expires_in_seconds = VERIFICATION_TOKEN_EXPIRE_HOURS * 3600
            await self._store_email_verification_token(created_user.email, verification_token, expires_in_seconds)
            await self.email_service.send_verification_email(created_user.email, created_user.username, verification_token)
            logger.info("Verification email initiated for %s", created_user.email)
        except Exception as e:
            # Log error but don't let it fail the registration process itself.
            # User can request a resend later.
            logger.error("Failed to send verification email for %s: %s", created_user.email, e)

        return created_user

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
        access_jti = uuid.uuid4().hex
        access_token = jwt.encode({"sub": email, "exp": access_expire, "type": "access", "jti": access_jti}, str(JWT_SECRET_KEY), algorithm="HS256")

        refresh_expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_jti = uuid.uuid4().hex
        refresh_token = jwt.encode(
            {"sub": email, "exp": refresh_expire, "type": "refresh", "jti": refresh_jti}, str(JWT_REFRESH_SECRET_KEY), algorithm="HS256"
        )

        logger.info("Tokens created for user: %s (Access JTI: %s, Refresh JTI: %s)", email, access_jti, refresh_jti)
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
            refresh_jti = payload.get("jti")

            if await self.is_jti_denylisted(refresh_jti):
                logger.warning("Denylisted refresh token presented for user: %s, JTI: %s", email, refresh_jti)
                return None

            if not email or token_type != "refresh":
                logger.warning("Refresh token validation failed for email: %s, type: %s", email, token_type)
                return None

            access_expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            new_access_jti = uuid.uuid4().hex
            new_access_token = jwt.encode(
                {"sub": email, "exp": access_expire, "type": "access", "jti": new_access_jti}, str(JWT_SECRET_KEY), algorithm="HS256"
            )
            logger.info("Access token refreshed for user: %s (New JTI: %s)", email, new_access_jti)
            return new_access_token

        except jwt.InvalidTokenError:
            logger.warning("Invalid refresh token presented.")
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

    async def login(self, user: UserLogin) -> Token:
        """Complete login flow with rate limiting."""
        # Check rate limiting first
        await self.rate_limit.check_failed_attempts(user.email)

        # Attempt authentication
        user_db = await self.authenticate_user(user.email, user.password)
        if not user_db:
            await self.rate_limit.record_failed_login(user.email)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

        # Success - clear rate limiting
        await self.rate_limit.clear_failed_attempts(user.email)
        access_token, refresh_token = await self.create_tokens(user_db.email)
        return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

    async def update_password(self, email: str, old_password: str, new_password: str) -> bool:
        """
        Update user's password with validation.

        Args:
            email: User's email
            old_password: Current password
            new_password: New password

        Returns:
            bool: True if password was updated

        Raises:
            HTTPException: If old password is incorrect or new password is weak
        """
        user = await self.authenticate_user(email, old_password)
        if not user:
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        if not self.is_strong_password(new_password):
            raise HTTPException(status_code=400, detail="New password is too weak")

        hashed_password = self.get_password_hash(new_password)
        await self.user_service.update_password(email, hashed_password)
        # Send notification email
        await self.email_service.send_password_change_notification(email, user.username)
        logger.info("Password updated for user: %s", email)
        return True

    async def initiate_password_reset(self, email: str) -> None:
        """Start password reset process."""
        user = await self.user_service.get_user(email)
        if not user:
            # Do not raise an error to prevent email enumeration.
            # Log the attempt for monitoring, if desired.
            logger.info("Password reset requested for non-existent email: %s", email)
            return  # Silently return

        reset_token = self._generate_reset_token(email)
        # Ensure username is available for the email template
        await self.email_service.send_reset_email(email=email, token=reset_token, username=user.username)
        logger.info("Password reset initiated for user: %s", email)

    async def complete_password_reset(self, token: str, new_password: str) -> bool:
        """Complete password reset with token."""
        try:
            payload = jwt.decode(token, str(JWT_SECRET_KEY), algorithms=["HS256"])
            email = payload["sub"]
            jti = payload.get("jti")

            if jti and await self.redis_service.get_cache(f"denylist_reset_token:{jti}"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token already used")

            if not self.is_strong_password(new_password):
                raise HTTPException(status_code=400, detail="Password too weak")

            hashed_password = self.get_password_hash(new_password)
            await self.user_service.update_password(email, hashed_password)

            if jti:
                await self.redis_service.set_cache(f"denylist_reset_token:{jti}", "used", ttl=self.password_reset_expiry + 60)

            # Send notification email after successful reset
            user = await self.user_service.get_user(email)  # Fetch user to get username
            if user:
                await self.email_service.send_password_change_notification(email, user.username)
            logger.info("Password reset completed for user: %s", email)
            return True
        except jwt.ExpiredSignatureError as exc:
            payload = {}  # Define payload in outer scope for logging
            try:
                payload = jwt.decode(token, str(JWT_SECRET_KEY), algorithms=[JWT_ALGORITHM], options={"verify_signature": False, "verify_exp": False})
            except jwt.InvalidTokenError:
                pass  # Ignore if unparseable, JTI won't be available
            logger.warning(
                "Expired password reset token presented for email: %s, JTI: %s", payload.get("sub", "unknown"), payload.get("jti", "unknown")
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token has expired") from exc
        except jwt.InvalidTokenError as exc:
            payload = {}  # Define payload in outer scope for logging
            try:
                payload = jwt.decode(token, str(JWT_SECRET_KEY), algorithms=[JWT_ALGORITHM], options={"verify_signature": False, "verify_exp": False})
            except jwt.InvalidTokenError:
                pass  # Ignore if unparseable, JTI won't be available
            logger.warning("Invalid password reset token presented. Email: %s, JTI: %s", payload.get("sub", "unknown"), payload.get("jti", "unknown"))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token") from exc

    def _generate_reset_token(self, email: str) -> str:
        """Generate password reset token."""
        expire = datetime.now(timezone.utc) + timedelta(seconds=self.password_reset_expiry)
        jti = uuid.uuid4().hex
        return jwt.encode({"sub": email, "exp": expire, "type": "reset", "jti": jti}, str(JWT_SECRET_KEY), algorithm="HS256")

    def _generate_alnum_token(self, length: int = 48) -> str:
        """Generates a cryptographically strong hexadecimal token."""
        num_bytes = (length + 1) // 2  # Each byte becomes 2 hex chars
        return secrets.token_hex(num_bytes)[:length]  # Generate enough bytes and trim to exact char length

    async def _store_email_verification_token(self, email: str, token: str, expires_in_seconds: int):
        """Stores email verification token in the database via UserService."""
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
            await self.user_service.store_email_verification_token(email, token, expires_at)
            logger.debug("Stored verification token for %s via UserService (expires at %s)", email, expires_at)
        except Exception as e:
            logger.error("Failed to store verification token for %s via UserService: %s", email, e)
            raise  # Re-raise to indicate failure

    async def get_email_by_verification_token(self, token: str) -> Optional[str]:
        """Retrieves email associated with a verification token from DB via UserService."""
        try:
            email = await self.user_service.get_user_email_by_verification_token(token)
            return email
        except Exception as e:
            logger.error("Failed to get verification token %s via UserService: %s", token, e)
            return None

    async def delete_email_verification_token(self, token: str):
        """Deletes an email verification token from DB via UserService."""
        try:
            await self.user_service.delete_verification_token(token)
            logger.debug("Deleted verification token %s via UserService", token)
        except Exception as e:
            logger.error("Failed to delete verification token %s via UserService: %s", token, e)
            # For deletion, we might not want to re-raise and break the flow, just log.

    async def verify_email_token(self, token: str) -> bool:
        """Verifies an email verification token, marks user as verified, and deletes token."""
        email_to_verify = await self.get_email_by_verification_token(token)

        if not email_to_verify:
            logger.warning("Attempt to verify email with invalid or expired token: %s", token)
            # Optionally, you could distinguish between expired and truly invalid if your token storage has expiry info
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")

        user = await self.user_service.get_user(email_to_verify)
        if not user:
            # This should ideally not happen if token mapping is correct
            logger.error("Verification token %s mapped to non-existent user %s", token, email_to_verify)
            # Still delete token to prevent reuse if it was somehow valid for a deleted user
            await self.delete_email_verification_token(token)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token. User not found.")

        # Mark user as verified in the database
        success = await self.user_service.mark_user_as_verified(user.email)
        if not success:
            # This could happen if the user was deleted between token check and this update,
            # or if there was a DB error during the update that mark_user_as_verified handled and returned False for.
            logger.error("Failed to mark user %s as verified in DB. mark_user_as_verified returned False.", user.email)
            # Token should still be deleted to prevent issues if it was valid.
            await self.delete_email_verification_token(token)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not verify email due to a server issue. Please try again or contact support.",
            )

        # Delete the token so it can't be reused
        await self.delete_email_verification_token(token)
        logger.info("Email successfully verified for user %s using token %s.", user.email, token)
        return True  # Or return the user object

    async def add_jti_to_denylist(self, jti: str, expires_in: int):
        """Adds a JTI to the denylist in Redis with an expiry."""
        if not jti:
            return
        try:
            await self.redis_service.set_cache(f"denylist_jti:{jti}", "revoked", ttl=expires_in)
            logger.info("JTI %s added to denylist for %s seconds.", jti, expires_in)
        except Exception as e:
            logger.error("Failed to add JTI %s to denylist: %s", jti, e)

    async def is_jti_denylisted(self, jti: str) -> bool:
        """Checks if a JTI is in the denylist."""
        if not jti:
            return False  # No JTI, so can't be denylisted
        try:
            return bool(await self.redis_service.get_cache(f"denylist_jti:{jti}"))
        except Exception as e:
            logger.error("Failed to check JTI %s in denylist: %s", jti, e)
            return False  # Fail safe: if error, assume not denylisted to avoid locking out users
