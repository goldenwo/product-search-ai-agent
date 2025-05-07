"""User service for managing user data in the database."""

from datetime import datetime, timezone
import os
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.user import UserCreate, UserInDB
from src.utils import logger
from src.utils.config import DATABASE_URL as DEFAULT_CONFIG_DATABASE_URL


class UserService:
    """Service for managing user data in the database."""

    def __init__(self):
        """Initialize database connection."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            db_url = DEFAULT_CONFIG_DATABASE_URL

        if not db_url:
            raise ValueError("DATABASE_URL is not set in environment or config.")

        if "YOUR_DATABASE_CONNECTION_STRING_HERE" in db_url or not (
            db_url.startswith("sqlite") or db_url.startswith("postgresql") or db_url.startswith("mysql")
        ):
            raise ValueError(f"Invalid or placeholder DATABASE_URL configured: {db_url}")

        self.engine = create_async_engine(str(db_url))
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def get_user(self, email: str) -> Optional[UserInDB]:
        """
        Retrieve a user from the database by email.

        Args:
            email: User's email address

        Returns:
            UserInDB if found, None otherwise
        """
        async with self.async_session() as session:
            result = await session.execute(
                text("SELECT email, username, hashed_password, is_verified FROM users WHERE email = :email"), {"email": email}
            )
            user_row = result.first()
            if user_row:
                user_data = {
                    "email": user_row.email,
                    "username": user_row.username,
                    "hashed_password": user_row.hashed_password,
                    "is_verified": user_row.is_verified if hasattr(user_row, "is_verified") else False,
                }
                return UserInDB.model_validate(user_data)
            return None

    async def create_user(self, user_data: UserCreate, hashed_password: str) -> UserInDB:
        """
        Create a new user in the database. is_verified defaults to FALSE.

        Args:
            user_data: User creation data
            hashed_password: Pre-hashed password

        Returns:
            UserInDB: Created user data

        Raises:
            SQLAlchemyError: If database operation fails
        """
        async with self.async_session() as session:
            async with session.begin():
                try:
                    result = await session.execute(
                        text("""
                        INSERT INTO users (email, username, hashed_password, is_verified)
                        VALUES (:email, :username, :hashed_password, FALSE)
                        RETURNING email, username, hashed_password, is_verified
                        """),
                        {"email": user_data.email, "username": user_data.username, "hashed_password": hashed_password},
                    )
                    user_row = result.first()
                    if user_row:
                        created_user_data = {
                            "email": user_row.email,
                            "username": user_row.username,
                            "hashed_password": user_row.hashed_password,
                            "is_verified": user_row.is_verified,
                        }
                        return UserInDB.model_validate(created_user_data)
                    logger.error("User creation with RETURNING did not yield a row.")
                    raise SQLAlchemyError("User creation failed to return user data.")
                except SQLAlchemyError as e:
                    logger.error("❌ Database error during user creation: %s", str(e))
                    raise

    async def update_password(self, email: str, hashed_password: str) -> None:
        """Update user's password in database."""
        async with self.async_session() as session:
            async with session.begin():
                try:
                    await session.execute(
                        text("UPDATE users SET hashed_password = :hashed_password WHERE email = :email"),
                        {"email": email, "hashed_password": hashed_password},
                    )
                    logger.info("Password updated in DB for %s", email)
                except SQLAlchemyError as e:
                    logger.error("❌ Database error updating password: %s", str(e))
                    raise

    async def store_email_verification_token(self, user_email: str, token: str, expires_at: datetime) -> None:
        """Stores an email verification token in the database."""
        async with self.async_session() as session:
            async with session.begin():
                try:
                    await session.execute(
                        text("""
                        INSERT INTO email_verification_tokens (user_email, token, expires_at)
                        VALUES (:user_email, :token, :expires_at)
                        """),
                        {"user_email": user_email, "token": token, "expires_at": expires_at},
                    )
                    logger.info("Stored verification token for %s", user_email)
                except SQLAlchemyError as e:
                    logger.error("❌ Database error storing verification token: %s", str(e))
                    raise

    async def get_user_email_by_verification_token(self, token: str) -> Optional[str]:
        """Retrieves a user's email by a valid (non-expired) verification token."""
        async with self.async_session() as session:
            try:
                current_time = datetime.now(timezone.utc)
                result = await session.execute(
                    text(""" 
                    SELECT user_email FROM email_verification_tokens
                    WHERE token = :token AND expires_at > :current_time
                    """),
                    {"token": token, "current_time": current_time},
                )
                record = result.first()
                return record.user_email if record else None
            except SQLAlchemyError as e:
                logger.error("❌ Database error fetching verification token: %s", str(e))
                return None

    async def mark_user_as_verified(self, email: str) -> bool:
        """Marks a user as verified in the database."""
        async with self.async_session() as session:
            async with session.begin():
                try:
                    result = await session.execute(text("UPDATE users SET is_verified = TRUE WHERE email = :email RETURNING email"), {"email": email})
                    updated_user = result.first()
                    if updated_user:
                        logger.info("User %s marked as verified in DB.", email)
                        return True
                    else:
                        logger.warning("Attempted to mark non-existent user %s as verified.", email)
                        return False
                except SQLAlchemyError as e:
                    logger.error("❌ Database error marking user %s as verified: %s", email, str(e))
                    raise

    async def delete_verification_token(self, token: str) -> None:
        """Deletes an email verification token from the database."""
        async with self.async_session() as session:
            async with session.begin():
                try:
                    await session.execute(text("DELETE FROM email_verification_tokens WHERE token = :token"), {"token": token})
                    logger.info("Deleted verification token: %s", token)
                except SQLAlchemyError as e:
                    logger.error("❌ Database error deleting verification token: %s", str(e))
                    pass
