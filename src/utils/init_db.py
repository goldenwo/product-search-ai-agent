"""One-time database initialization script."""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from src.db.models import EmailVerificationToken, Product, User  # noqa: F401
from src.schemas.base import Base
from src.utils.config import DATABASE_URL


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
