import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure this path is correct to import your Base and init_db logic
# If init_db also defines Base, that's fine. Otherwise, import Base separately if needed.
from src.utils.init_db import Base  # Assuming Base is accessible here

# Use a file-based SQLite database for easier inspection during test development
TEST_SQLITE_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
# For purely in-memory (faster, ephemeral):
# TEST_SQLITE_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def set_test_environment_variables():
    """
    Set environment variables for the test session.
    This runs once per test session before any tests are collected.
    """
    os.environ["DATABASE_URL"] = TEST_SQLITE_DATABASE_URL
    # Override other necessary environment variables for testing
    os.environ["OPENAI_API_KEY"] = "TEST_OPENAI_KEY"
    os.environ["SERP_API_KEY"] = "TEST_SERP_API_KEY"
    os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_for_unit_tests"
    os.environ["JWT_REFRESH_SECRET_KEY"] = "test_jwt_refresh_secret_key_for_unit_tests"
    os.environ["SENDGRID_API_KEY"] = "TEST_SENDGRID_KEY"  # So EmailService can init without error

    print(f"DATABASE_URL for test session set to: {os.getenv('DATABASE_URL')}")


@pytest.fixture(scope="session")
async def db_engine_with_schema():
    """
    Provides a SQLAlchemy engine for the test session.
    The schema (tables) is created once per session.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # This should ideally be caught by the set_test_environment_variables fixture
        raise ValueError("DATABASE_URL not set for tests. Ensure set_test_environment_variables fixture ran.")

    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        # Optional: Drop all tables first for a clean state in file-based DB
        # Be cautious if you ever point this to a non-test DB.
        # Usually for file/memory based test DBs, starting fresh is good.
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine  # Provide the engine

    # Teardown for the engine after the entire test session
    await engine.dispose()

    # Optional: Clean up the test.db file if it's file-based and you want a fresh one next time
    if TEST_SQLITE_DATABASE_URL.startswith("sqlite+aiosqlite:///./"):
        db_file_path = TEST_SQLITE_DATABASE_URL.split("///./")[1]
        if os.path.exists(db_file_path):
            # print(f"Cleaning up test database file: {db_file_path}")
            # os.remove(db_file_path) # Uncomment if you want to delete the .db file after each session
            pass


@pytest.fixture(scope="function")
async def db_session_for_test(db_engine_with_schema):
    """
    This fixture ensures the database schema is set up (via db_engine_with_schema).
    Individual tests that use UserService will then create their own sessions
    using the globally (for tests) configured DATABASE_URL.

    If you need to manage transactions per test function explicitly with a shared session,
    this fixture could be expanded to yield an AsyncSession. For now, its main role
    is to ensure db_engine_with_schema has run.
    """
    # The main purpose is to ensure db_engine_with_schema (which creates tables) has run.
    # Actual session usage will be within UserService, which creates its own sessions.
    yield
    # If you needed to clean up data from tables after each test function, you could do it here.
    # For example, for each table:
    # async with db_engine_with_schema.connect() as connection:
    #     await connection.execute(text(f"DELETE FROM {table_name}"))
    #     await connection.commit()
    # This is more complex and often handled by full transactional tests or ORM session rollbacks.
    # Given UserService uses session.begin(), rollbacks on error are handled there.
    # Full data cleanup between tests might be needed if tests have side effects on shared data.
