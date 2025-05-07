import asyncio

# import os # Removed as os.path/remove are no longer used for in-memory db
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.asyncio import Redis as AsyncRedisClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src import dependencies
from src.services.redis_service import RedisService

# Ensure this path is correct to import your Base and init_db logic
# If init_db also defines Base, that's fine. Otherwise, import Base separately if needed.
# Explicitly import models to ensure they are registered with Base.metadata before create_all
from src.utils.init_db import (
    Base,  # Assuming Base is accessible here
    EmailVerificationToken,  # noqa: F401
    User,  # noqa: F401
)

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop(request):
    """Redefine the event_loop fixture to have session scope.
    This is necessary for session-scoped async fixtures.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")  # No longer autouse, will be pulled in by mock_global_dependencies...
def set_test_environment(session_monkeypatch):  # Use a session-scoped monkeypatch
    """Set environment variables for the test session."""
    session_monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    session_monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_key_for_testing_!@#$")
    session_monkeypatch.setenv("JWT_REFRESH_SECRET_KEY", "test_jwt_refresh_secret_key_for_testing_!@#$")
    session_monkeypatch.setenv("SENDGRID_API_KEY", "test_sendgrid_api_key")
    session_monkeypatch.setenv("OPENAI_API_KEY", "test_openai_api_key")
    session_monkeypatch.setenv("SERP_API_KEY", "test_serp_api_key")
    session_monkeypatch.setenv("ENVIRONMENT", "test")  # Ensures IS_DEVELOPMENT might be false if needed
    # Add any other environment variables required by your application during tests


@pytest.fixture(scope="session")
def session_monkeypatch():
    """A session-scoped monkeypatch.
    Note: MonkeyPatch itself is designed for function scope for easy cleanup.
    This provides a way to use its setenv/delenv for session setup.
    Be cautious with other monkeypatch features like patching objects,
    as their lifecycle might not align with session scope as cleanly.
    """
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope="session")
async def db_engine_with_schema(set_test_environment, event_loop):
    """
    Creates a test database engine and initializes the schema once per session.
    Depends on set_test_environment to ensure DATABASE_URL is correctly set.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        # Ensure all tables defined by Base.metadata are created.
        await conn.run_sync(Base.metadata.create_all)

    yield engine  # Provide the engine to other fixtures/tests

    # Teardown: Drop all tables after the test session.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    # No file to remove for in-memory databases
    # if TEST_DATABASE_URL.startswith("sqlite+") and "memory" not in TEST_DATABASE_URL:
    #     db_file_path = TEST_DATABASE_URL.split("///")[-1]
    #     if os.path.exists(db_file_path):
    #         try:
    #             os.remove(db_file_path)
    #         except OSError as e:
    #             print(f"Warning: Could not remove test database file {db_file_path}: {e}")


@pytest.fixture(scope="function")
async def db_session_for_test(db_engine_with_schema):
    """
    Provides a database session for a single test function.
    Ensures the session is rolled back after the test.
    """
    # db_engine_with_schema is the engine instance yielded by the session-scoped fixture
    async_session_factory = async_sessionmaker(bind=db_engine_with_schema, class_=AsyncSession, expire_on_commit=False)
    async with async_session_factory() as session:
        try:
            yield session
            # If you want to commit changes made during a test:
            # await session.commit()
        except:  # noqa
            await session.rollback()  # Rollback on any exception during the test
            raise
        finally:
            await session.close()  # Ensure session is closed


# --- Global Mocking for dependencies used in lifespan ---
# This fixture helps ensure that services obtained by main.lifespan
# (which creates app.state.auth_service) don't use real external services
# unless specifically intended (like UserService with a test DB).
@pytest.fixture(scope="session", autouse=True)
def mock_global_dependencies_for_lifespan(set_test_environment):  # Depends on session-scoped set_test_environment
    original_redis_in_cache = dependencies._cache.get("redis")
    mock_redis_service_instance = MagicMock(spec=RedisService)
    mock_redis_service_instance.redis = AsyncMock(spec=AsyncRedisClient)
    mock_redis_service_instance.get_cache = AsyncMock(return_value=None)
    mock_redis_service_instance.set_cache = AsyncMock()
    mock_redis_service_instance.delete_cache = AsyncMock()
    dependencies._cache["redis"] = mock_redis_service_instance
    yield
    if original_redis_in_cache:
        dependencies._cache["redis"] = original_redis_in_cache
    elif "redis" in dependencies._cache:
        del dependencies._cache["redis"]
