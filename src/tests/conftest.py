import asyncio
import logging
import os
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI

# from dotenv import load_dotenv # Removed by user, re-evaluate if needed
from httpx import ASGITransport, AsyncClient

# from sqlalchemy.orm import sessionmaker # Removed by user, was previously commented out or unused
# Import MemoryStorage for mocking limiter
from limits.storage import MemoryStorage
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import the global limiter instance to patch its storage
from src.dependencies import limiter

# If you have other models in src/models/ that use the same Base, import them too:
# from src.models.some_other_model import SomeOtherModel
from src.main import app as fastapi_app
from src.models.base import Base  # This import needs src/models/base.py to define Base
from src.services.auth_service import AuthService
from src.services.email_service import EmailService
from src.services.redis_service import RedisService
from src.services.user_service import UserService
from src.utils.config import (  # noqa. Re-adding this critical import
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
# Ensure models are imported before this fixture is defined so Base.metadata knows about them
@pytest.fixture(scope="session")
async def db_engine_with_schema(set_test_environment):
    """
    Creates a test database engine and initializes the schema once per session.
    Depends on set_test_environment to ensure DATABASE_URL is correctly set.
    """
    # Ensure set_test_environment has run
    engine = create_async_engine(TEST_DATABASE_URL)  # Use the test URL
    async with engine.begin() as conn:
        # Ensure all tables defined by Base.metadata are created.
        # This requires User, EmailVerificationToken etc. to be imported somewhere to register with Base.
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"Database schema created at {TEST_DATABASE_URL}")

    yield engine  # Provide the engine to other fixtures/tests

    # Teardown: Drop all tables after the test session.
    logger.info(f"Dropping database schema at {TEST_DATABASE_URL}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    # Remove the SQLite file after tests if it's not an in-memory DB
    if TEST_DATABASE_URL.startswith("sqlite+") and "memory" not in TEST_DATABASE_URL:
        db_file_path = TEST_DATABASE_URL.split("///")[-1]
        if os.path.exists(db_file_path):
            try:
                os.remove(db_file_path)
                logger.info(f"Test database file {db_file_path} removed.")
            except OSError as e:
                logger.warning(f"Warning: Could not remove test database file {db_file_path}: {e}")


@pytest.fixture(scope="function")
async def db_session_for_test(db_engine_with_schema):  # Depends on the session-scoped engine
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
            # await session.commit() # Typically not done in unit/integration tests to keep them isolated
        except:  # noqa
            await session.rollback()  # Rollback on any exception during the test
            raise
        finally:
            await session.close()  # Ensure session is closed


# --- Application and Client Fixtures ---
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def app(event_loop, mock_global_dependencies_for_lifespan):  # Ensure lifespan dependencies are mocked
    """
    Fixture to provide the FastAPI application instance for testing.
    This is session-scoped as the app structure doesn't change per test.
    """
    # The app is imported as fastapi_app to avoid name collision
    # mock_global_dependencies_for_lifespan will ensure app.state.auth_service.redis_service is mocked
    return fastapi_app


@pytest.fixture(scope="function")
async def client(app: FastAPI):  # Explicitly type hint the app fixture parameter
    """
    Fixture to provide an HTTPX AsyncClient for making requests to the test application.
    """
    # Pass the app instance, now explicitly typed, to ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Service Mocks and Fixtures ---


@pytest.fixture(scope="session", autouse=True)
def mock_global_dependencies_for_lifespan(session_monkeypatch, set_test_environment):
    """
    Mocks global dependencies that might be initialized during FastAPI lifespan,
    BEFORE the app or client fixtures are set up.
    Specifically targets RedisService used by AuthService on app.state by patching
    the `get_redis_service` dependency getter.
    """
    logger.info("Patching src.dependencies.get_redis_service to return a mock RedisService for the session.")

    # 1. Create a fully configured mock RedisService instance
    mock_redis_instance = MagicMock(spec=RedisService)
    mock_redis_instance.client = AsyncMock()  # Mock the underlying redis client attribute
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
    # You can add other methods/attributes if AuthService or RedisService itself uses them upon init
    # For example, if RedisService sets up its own redis_url:
    # mock_redis_instance.redis_url = f"redis://mock_host:1234/9"

    # 2. Patch the getter function in src.dependencies
    # This ensures that when main.py's lifespan calls get_redis_service(),
    # it receives our mock_redis_instance.
    session_monkeypatch.setattr("src.dependencies.get_redis_service", lambda: mock_redis_instance)

    # Also, to be thorough, if dependencies._cache is used by get_redis_service,
    # you might want to directly set the cache entry if the setattr on the getter isn't enough
    # or if other parts of the code might access dependencies._cache["redis"] directly.
    # from src import dependencies # if not already imported at top level of conftest
    # dependencies._cache["redis"] = mock_redis_instance
    # However, patching the getter is generally cleaner if that's the sole entry point.

    logger.info("src.dependencies.get_redis_service patched to return a specific mock RedisService instance.")

    # The original __init__ patching is no longer needed:
    # def mock_redis_init(self, host, port, db, password=None):
    #     ...
    # session_monkeypatch.setattr(RedisService, "__init__", mock_redis_init)


@pytest.fixture
def mock_user_service():
    service = MagicMock(spec=UserService)
    # Define responses for commonly used async methods
    service.create_user = AsyncMock()
    service.get_user_by_email = AsyncMock(return_value=None)
    service.get_user_by_username = AsyncMock(return_value=None)
    service.get_user_by_id = AsyncMock(return_value=None)
    service.verify_user_email = AsyncMock()
    service.update_user_password = AsyncMock()
    service.create_email_verification_token = AsyncMock(return_value="test_token_123")
    service.get_email_verification_token = AsyncMock(return_value=None)
    service.delete_email_verification_token = AsyncMock()
    return service


@pytest.fixture
def mock_email_service():
    service = MagicMock(spec=EmailService)
    service.send_verification_email = AsyncMock()
    service.send_password_reset_email = AsyncMock()
    service.send_password_changed_email = AsyncMock()
    return service


@pytest.fixture
def mock_redis_service():
    """Provides a MagicMock for RedisService for direct injection if needed."""
    mock_service = MagicMock(spec=RedisService)
    mock_service.get_value = AsyncMock(return_value=None)
    mock_service.set_value = AsyncMock()
    mock_service.delete_value = AsyncMock()
    mock_service.increment_value = AsyncMock(return_value=1)
    mock_service.get_int_value = AsyncMock(return_value=0)
    mock_service.set_value_with_expiry = AsyncMock()
    mock_service.exists = AsyncMock(return_value=False)
    mock_service.sadd = AsyncMock()
    mock_service.sismember = AsyncMock(return_value=False)
    mock_service.ping = AsyncMock(return_value=True)
    mock_service.close = AsyncMock()
    return mock_service


@pytest.fixture
def mocked_auth_service(mock_user_service, mock_redis_service, mock_email_service):
    """
    Provides an AuthService instance with mocked dependencies.
    """
    # set_test_environment (autouse=True) ensures JWT env vars are set
    auth_service = AuthService(
        user_service=mock_user_service,
        redis_service=mock_redis_service,  # Uses the function-scoped mock here
        email_service=mock_email_service,
    )
    return auth_service
