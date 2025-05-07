import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure this path is correct to import your Base and init_db logic
# If init_db also defines Base, that's fine. Otherwise, import Base separately if needed.
from src.utils.init_db import Base  # Assuming Base is accessible here

# Use a file-based SQLite database for easier inspection during test development
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
# For purely in-memory (faster, ephemeral):
# TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop(request):
    """Redefine the event_loop fixture to have session scope.
    This is necessary for session-scoped async fixtures.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def set_test_environment(monkeypatch):
    """Set environment variables for the test session."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_key_for_testing_!@#$")
    monkeypatch.setenv("JWT_REFRESH_SECRET_KEY", "test_jwt_refresh_secret_key_for_testing_!@#$")
    monkeypatch.setenv("SENDGRID_API_KEY", "test_sendgrid_api_key")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_api_key")
    monkeypatch.setenv("SERP_API_KEY", "test_serp_api_key")
    monkeypatch.setenv("ENVIRONMENT", "test")  # Ensures IS_DEVELOPMENT might be false if needed
    # Add any other environment variables required by your application during tests


@pytest.fixture(scope="session")
async def db_engine_with_schema(set_test_environment, event_loop):  # event_loop is now session-scoped
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

    # Optional: Remove the test database file if it's file-based
    if TEST_DATABASE_URL.startswith("sqlite+") and "memory" not in TEST_DATABASE_URL:
        db_file_path = TEST_DATABASE_URL.split("///")[-1]
        if os.path.exists(db_file_path):
            try:
                os.remove(db_file_path)
            except OSError as e:
                # Log error if removal fails, but don't fail the tests
                print(f"Warning: Could not remove test database file {db_file_path}: {e}")


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
def mock_global_dependencies_for_lifespan(set_test_environment):  # Depends on env vars being set
    from unittest.mock import AsyncMock, MagicMock

    from redis.asyncio import Redis as AsyncRedisClient  # For spec

    from src import dependencies  # Target where get_... is defined
    from src.services.redis_service import RedisService

    # --- Mock RedisService for lifespan ---
    # Store original if it exists, to restore later
    original_redis_in_cache = dependencies._cache.get("redis")

    mock_redis_service_instance = MagicMock(spec=RedisService)
    # Mock the actual redis client attribute within RedisService
    mock_redis_service_instance.redis = AsyncMock(spec=AsyncRedisClient)

    # Mock methods of RedisService that the real AuthService (in app.state) might call
    # Default behavior for is_jti_denylisted checks
    mock_redis_service_instance.get_cache = AsyncMock(return_value=None)
    mock_redis_service_instance.set_cache = AsyncMock()
    mock_redis_service_instance.delete_cache = AsyncMock()
    # Add other methods if the real AuthService in app.state calls them

    # Override the cached instance in dependencies module
    dependencies._cache["redis"] = mock_redis_service_instance

    # Potentially mock other services like EmailService if its client makes real calls
    # For UserService, conftest already sets up a test DB, so direct calls are okay for testing UserService itself.
    # The real AuthService in app.state will use this test DB via the real UserService.

    yield  # Tests run here

    # --- Restore original state of dependencies._cache ---
    if original_redis_in_cache:
        dependencies._cache["redis"] = original_redis_in_cache
    elif "redis" in dependencies._cache:  # If it was set by us and not there before
        del dependencies._cache["redis"]

    # Restore other mocked services if any were globally mocked here
