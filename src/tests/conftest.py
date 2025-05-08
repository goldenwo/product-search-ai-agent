import asyncio
import logging
import os
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI

# Import MemoryStorage for mocking limiter
from limits.storage import MemoryStorage
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Import the global limiter instance to patch its storage
from src.dependencies import limiter

# If you have other models in src/models/ that use the same Base, import them too:
from src.main import app as fastapi_app
from src.models.base import Base  # This import needs src/models/base.py to define Base
from src.services.auth_service import AuthService
from src.services.email_service import EmailService
from src.services.redis_service import RedisService
from src.services.user_service import UserService
from src.utils.config import (  # noqa
    DATABASE_URL,  # noqa: F401
    JWT_ALGORITHM,  # noqa: F401
    JWT_SECRET_KEY,  # noqa: F401
    REDIS_DB,  # noqa: F401
    REDIS_HOST,  # noqa: F401
    REDIS_PORT,  # noqa: F401
)
from src.utils.init_db import EmailVerificationToken, User  # noqa: F401

# Import models to ensure Base.metadata is populated before create_all

# Configure logger for tests
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@pytest.fixture(scope="session")
def event_loop(request):
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Determine the test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
# Ensure this path is correct to import your Base and init_db logic
# from src.database.setup import Base, init_db # Adjust if you have a central db setup


# --- Environment Setup ---
@pytest.fixture(scope="session")
def session_monkeypatch():
    """A session-scoped monkeypatch utility."""
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope="session", autouse=True)
def set_test_environment(session_monkeypatch):
    """
    Sets environment variables for the test session.
    This runs once per session and is autouse=True to apply to all tests.
    """
    logger.info("Setting test environment variables for the session.")
    session_monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    session_monkeypatch.setenv("REDIS_HOST", "localhost")  # Or mock Redis host
    session_monkeypatch.setenv("REDIS_PORT", "6379")  # Or mock Redis port
    session_monkeypatch.setenv("REDIS_DB", "1")  # Use a different DB for tests if real Redis is used
    session_monkeypatch.setenv("TESTING", "True")
    session_monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_for_tests_!@#123")
    session_monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    session_monkeypatch.setenv("EMAIL_SENDER", "test_sender@example.com")
    session_monkeypatch.setenv("SENDGRID_API_KEY", "dummy_sendgrid_key_for_tests")
    session_monkeypatch.setenv("FRONTEND_URL", "http://localhost:8001")  # Dummy frontend URL for tests

    # Reload config if your app loads it at module level, or ensure services pick up new env vars
    # from src.utils import config
    # import importlib
    # importlib.reload(config)
    logger.info(f"DATABASE_URL set to: {os.getenv('DATABASE_URL')}")


@pytest.fixture(scope="session", autouse=True)
def mock_limiter_storage_for_tests(session_monkeypatch):
    """
    Patches the global limiter's storage to use MemoryStorage for the test session.
    This prevents tests from trying to connect to a real Redis instance for rate limiting.
    """
    logger.info("Patching global limiter storage with MemoryStorage for test session.")
    memory_storage_instance = MemoryStorage()
    # Patch the 'storage' attribute of the INNER limiter object
    # The SlowAPI Limiter instance often holds the actual rate limiter from the 'limits' library
    # in an attribute like '_limiter' or 'limiter'. We need to inspect the SlowAPI Limiter object
    # or its source to be sure, but 'limiter.limiter.storage' is a common pattern if it wraps
    # another limiter.
    # If 'limiter.limiter' doesn't exist, we might need to re-initialize the SlowAPI limiter
    # with a new storage_options or a direct MemoryStorage instance if its API allows.

    # Let's try patching what is typically the path to the actual storage backend.
    # The SlowAPI.Limiter itself might not have a direct .storage attribute for setting.
    # It often has a .limiter attribute which is the instance from the 'python-limits' library.
    if hasattr(limiter, "limiter") and hasattr(limiter.limiter, "storage"):
        session_monkeypatch.setattr(limiter.limiter, "storage", memory_storage_instance)
        logger.info("Patched limiter.limiter.storage with MemoryStorage instance.")
    elif hasattr(limiter, "_limiter") and hasattr(limiter._limiter, "storage"):
        session_monkeypatch.setattr(limiter._limiter, "storage", memory_storage_instance)
        logger.info("Patched limiter._limiter.storage with MemoryStorage instance.")
    else:
        # Fallback or error if the structure isn't as expected.
        # This might happen if SlowAPI changes its internal structure.
        # A more robust way might be to re-initialize the limiter with a memory storage URI
        # if the current `limiter` object in dependencies allows for such re-configuration,
        # or by patching the storage_uri before the limiter is first accessed/initialized.
        logger.error(
            "Could not find the correct path to patch limiter storage. "
            "The internal structure of SlowAPI.Limiter might have changed. "
            "Attempting to set storage_uri and re-initialize (conceptual)."
        )
        # This conceptual part is tricky to do post-initialization without re-creating the limiter.
        # For now, we'll raise an error if the common paths aren't found.
        raise AttributeError("Could not patch limiter storage. Check SlowAPI Limiter internal structure.")


# --- Database Fixtures ---


@pytest.fixture(scope="session")
def db_engine(set_test_environment):
    """
    Synchronously creates the test database engine once per session.
    Ensures the test database file is removed before starting if it exists.
    Yields the engine instance. Disposal is handled by _manage_db_engine_lifecycle.
    """
    db_file_path = None
    if TEST_DATABASE_URL.startswith("sqlite+") and "memory" not in TEST_DATABASE_URL:
        db_file_path = TEST_DATABASE_URL.split("///")[-1]
        if os.path.exists(db_file_path):
            try:
                logger.info(f"Attempting to remove existing test database file: {db_file_path}")
                os.remove(db_file_path)
                logger.info(f"Successfully removed existing test database file: {db_file_path}")
            except OSError as e:
                logger.error(f"Error removing existing test database file {db_file_path} during setup: {e}. Tests may fail or be unreliable.")

    # Engine creation itself is synchronous
    engine = create_async_engine(TEST_DATABASE_URL)
    logger.info(f"Database engine created for {TEST_DATABASE_URL}")

    yield engine  # Provide the engine instance

    # Teardown: File removal (Disposal handled separately)
    logger.info("db_engine fixture teardown: File removal check.")
    # await engine.dispose() # REMOVED - Handled by _manage_db_engine_lifecycle

    if db_file_path and os.path.exists(db_file_path):
        try:
            logger.info(f"Attempting final removal of test database file {db_file_path} post-session.")
            os.remove(db_file_path)
            logger.info(f"Test database file {db_file_path} removed after session.")
        except OSError as e:
            logger.warning(f"Warning: Could not remove test database file {db_file_path} post-session: {e}. It might be locked.")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_db_engine_lifecycle(db_engine: AsyncEngine):
    """Automatically disposes the session-scoped engine at the end of the test session."""
    yield  # Fixture does setup/teardown via dependency and finally block
    # Teardown: Dispose the engine asynchronously
    logger.info(f"_manage_db_engine_lifecycle: Disposing engine {db_engine}")
    try:
        await db_engine.dispose()
        logger.info("_manage_db_engine_lifecycle: Engine disposed successfully.")
    except Exception as e:
        logger.error(f"_manage_db_engine_lifecycle: Error disposing engine: {e}")


@pytest_asyncio.fixture(scope="function")
async def initialize_schema(db_engine: AsyncEngine):
    """
    Initializes the database schema at the start of each function/test and drops it at the end.
    """
    try:
        async with db_engine.begin() as conn:
            logger.info("Initializing schema via initialize_schema fixture...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database schema created.")
        yield  # Ready for tests
    finally:
        # Teardown: Drop tables and dispose engine
        logger.info("Dropping schema via initialize_schema fixture...")
        try:
            async with db_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.info("Successfully dropped all tables.")
        except Exception as e:
            logger.error(f"Error dropping tables: {e}")

        # logger.info(f"Disposing engine via initialize_schema fixture...") # Removed
        # await db_engine.dispose() # Removed


@pytest_asyncio.fixture(scope="function")
async def db_session_for_test(db_engine: AsyncEngine, initialize_schema):  # Depends on engine AND schema being ready
    """
    Provides a database session for a single test function.
    Ensures the session is rolled back after the test.
    Depends on db_engine and initialize_schema.
    """
    async_session_factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# --- Application and Client Fixtures ---


# Simple fixture returning the app instance
@pytest.fixture(scope="session")
def app() -> FastAPI:
    """Provides the raw FastAPI app instance (session-scoped)."""
    return fastapi_app


# Async fixture to manage app state setup/teardown for the session
@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_app_state(app: FastAPI, mock_global_dependencies_for_lifespan):
    """
    Sets up and tears down app.state for the test session.
    Runs automatically due to autouse=True.
    Depends on the 'app' fixture and mock setup.
    """
    # Create mocks needed for app.state.auth_service
    mock_redis_s = MagicMock(spec=RedisService)
    mock_redis_s.redis = AsyncMock()
    mock_user_s = MagicMock(spec=UserService)
    mock_user_s.get_user = AsyncMock(return_value=None)
    mock_email_s = MagicMock(spec=EmailService)
    mock_email_s.send_verification_email = AsyncMock()

    # Create the AuthService instance for app.state
    mock_auth_s_for_state = AuthService(redis_service=mock_redis_s, user_service=mock_user_s, email_service=mock_email_s)
    mock_auth_s_for_state.rate_limit.redis = mock_redis_s.redis

    # Explicitly configure methods on the state mock needed by middleware
    mock_auth_s_for_state.is_jti_denylisted = AsyncMock(return_value=False)
    mock_auth_s_for_state.add_jti_to_denylist = AsyncMock()  # Configure add method as well
    # Add other methods if middleware were to call them

    # Set state on the app instance provided by the 'app' fixture
    app.state.auth_service = mock_auth_s_for_state
    app.state.limiter = limiter  # Global limiter instance
    logger.info("Session-scoped app state setup completed (State AuthService configured).")

    yield  # Let the session run

    # Teardown state
    logger.info("Session-scoped app state teardown.")
    if hasattr(app.state, "auth_service"):
        delattr(app.state, "auth_service")
    if hasattr(app.state, "limiter"):
        delattr(app.state, "limiter")


# --- Service Mocks and Fixtures ---


# mock_global_dependencies_for_lifespan remains session-scoped, autouse=True
@pytest.fixture(scope="session", autouse=True)
def mock_global_dependencies_for_lifespan(session_monkeypatch, set_test_environment):
    """
    Mocks global dependencies (like RedisService getter) needed BEFORE app/lifespan.
    Session-scoped and autouse.
    """
    logger.info("Patching src.dependencies.get_redis_service for session scope.")
    mock_redis_instance = MagicMock(spec=RedisService)
    mock_redis_instance.redis = AsyncMock()
    mock_redis_instance.get_value = AsyncMock(return_value=None)
    mock_redis_instance.set_value = AsyncMock()
    mock_redis_instance.delete_value = AsyncMock()
    mock_redis_instance.increment_value = AsyncMock(return_value=1)
    mock_redis_instance.get_int_value = AsyncMock(return_value=0)
    mock_redis_instance.set_value_with_expiry = AsyncMock()
    mock_redis_instance.exists = AsyncMock(return_value=False)
    mock_redis_instance.sadd = AsyncMock()
    mock_redis_instance.sismember = AsyncMock(return_value=False)
    mock_redis_instance.ping = AsyncMock(return_value=True)
    mock_redis_instance.close = AsyncMock()
    session_monkeypatch.setattr("src.dependencies.get_redis_service", lambda: mock_redis_instance)
    logger.info("src.dependencies.get_redis_service patched for session scope.")
    # No return value needed now


# ... (rest of fixtures)
