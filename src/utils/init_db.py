"""One-time database initialization script."""

import asyncio

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String  # Add Boolean, ForeignKey, DateTime, Integer, func
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base

from src.utils.config import DATABASE_URL

Base = declarative_base()


class User(Base):
    """Database model for user table."""

    __tablename__ = "users"
    email = Column(String, primary_key=True, index=True)
    username = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)  # Added is_verified


class EmailVerificationToken(Base):
    """Database model for email_verification_tokens table."""

    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)  # Standard integer primary key
    user_email = Column(String, ForeignKey("users.email", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    # created_at = Column(DateTime(timezone=True), server_default=func.now()) # Optional: for tracking creation time


async def init_db():
    """
    Initialize database tables.

    Creates all tables defined in SQLAlchemy models if they don't exist.

    Raises:
        ValueError: If DATABASE_URL is not set
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL must be set")

    engine = create_async_engine(str(DATABASE_URL))
    async with engine.begin() as conn:
        # This will create tables if they don't exist.
        # It will NOT update existing tables if their schema changes (e.g., adding is_verified to an existing users table).
        # For schema migrations on existing tables, you'd typically use a migration tool like Alembic.
        await conn.run_sync(Base.metadata.create_all)

    # Optional: You might want to close the engine if the script is short-lived,
    # though for a one-off script it might not be strictly necessary.
    await engine.dispose()
    print("Database tables initialized (if they did not already exist).")


if __name__ == "__main__":
    asyncio.run(init_db())
