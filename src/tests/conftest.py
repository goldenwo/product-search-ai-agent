"""Pytest fixtures for FastAPI app, database, and rate limiter used in tests."""

import asyncio
import os
from typing import AsyncGenerator

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.main import app as fastapi_app
from src.schemas.base import Base

# Define test DB URL locally to avoid importing config (which binds env too early)
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# Ensure the app-level DATABASE_URL points to the test DB before importing app or session-related modules
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture(scope="session")
def app():
    """Provide the FastAPI app instance as a test fixture."""
    return fastapi_app


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for session-scoped async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def set_test_environment():
    """Compatibility fixture used by some tests to ensure env is set."""
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    yield


@pytest.fixture(scope="session", autouse=True)
def patch_rate_limiter_storage_and_attach(app):
    """Use in-memory storage for SlowAPI limiter and attach to app.state."""
    from limits.storage import MemoryStorage

    from src.dependencies import limiter

    storage = MemoryStorage()
    if hasattr(limiter, "limiter") and hasattr(limiter.limiter, "storage"):
        limiter.limiter.storage = storage
    elif hasattr(limiter, "_limiter") and hasattr(limiter._limiter, "storage"):
        limiter._limiter.storage = storage
    # Ensure handler can access limiter
    app.state.limiter = limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter(app):
    """Reset limiter storage before each test to avoid cross-test interference."""
    from limits.storage import MemoryStorage

    from src.dependencies import limiter

    storage = MemoryStorage()
    if hasattr(limiter, "limiter") and hasattr(limiter.limiter, "storage"):
        limiter.limiter.storage = storage
    elif hasattr(limiter, "_limiter") and hasattr(limiter._limiter, "storage"):
        limiter._limiter.storage = storage
    app.state.limiter = limiter


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Set up and tear down the test database schema once per session."""
    # Ensure models are imported so Base.metadata is populated
    from src.db import models as _models  # noqa: F401

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Function-scoped AsyncEngine with isolated schema for integration tests."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Provide a test client with an isolated DB session for each test."""
    engine = create_async_engine(TEST_DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        # Import lazily so that env is already set and engine isn't created at import time with bad URL
        from src.dependencies import get_db_session  # noqa: WPS433

        def override_get_db_session():
            yield session

        app.dependency_overrides[get_db_session] = override_get_db_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

        app.dependency_overrides.clear()

    await engine.dispose()
