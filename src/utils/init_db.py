"""One-time database initialization script."""

import asyncio

from sqlalchemy import Column, String
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
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
