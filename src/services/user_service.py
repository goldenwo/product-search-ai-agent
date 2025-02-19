"""User service for managing user data in the database."""

from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.user import UserCreate, UserInDB
from src.utils import logger
from src.utils.config import DATABASE_URL


class UserService:
    """Service for managing user data in the database."""

    def __init__(self):
        """Initialize database connection."""
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL must be set")
        self.engine = create_async_engine(str(DATABASE_URL))
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
            result = await session.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
            user = result.first()
            return UserInDB.model_validate(user) if user else None

    async def create_user(self, user_data: UserCreate, hashed_password: str) -> UserInDB:
        """
        Create a new user in the database.

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
                        INSERT INTO users (email, username, hashed_password)
                        VALUES (:email, :username, :hashed_password)
                        RETURNING *
                        """),
                        {"email": user_data.email, "username": user_data.username, "hashed_password": hashed_password},
                    )
                    user = result.first()
                    await session.commit()
                    return UserInDB.model_validate(user)
                except SQLAlchemyError as e:
                    await session.rollback()
                    logger.error("❌ Database error: %s", str(e))
                    raise
