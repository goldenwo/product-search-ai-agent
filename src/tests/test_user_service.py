"""Test the UserService class."""

from unittest.mock import AsyncMock, Mock

# Helper for hashing in tests if AuthService is not instantiated
# For real AuthService, use its get_password_hash and verify_password
from passlib.hash import bcrypt
from pydantic import ValidationError
import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.models.user import UserCreate, UserInDB
from src.services.user_service import UserService


def get_test_password_hash(password: str) -> str:
    return bcrypt.hash(password)


def verify_test_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.verify(plain_password, hashed_password)


@pytest.fixture
def mocked_user_service(set_test_environment):
    """Create UserService instance with all database interactions mocked."""
    service = UserService()
    mock_session = AsyncMock()

    mock_result_object = Mock()

    # This is what result.first() will return in the mocked scenario.
    # It needs to have an _asdict() method.
    mock_row_object = Mock()
    mock_result_object.first = Mock(return_value=mock_row_object)  # .first() returns our mock_row_object

    mock_result_object.scalar_one_or_none = Mock(return_value=None)
    mock_result_object.one = Mock()
    mock_result_object.all = Mock(return_value=[])

    mock_session.execute = AsyncMock(return_value=mock_result_object)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    mock_trans = AsyncMock()
    mock_trans.__aenter__ = AsyncMock(return_value=mock_session)
    mock_trans.__aexit__ = AsyncMock(return_value=False)
    mock_session.begin = Mock(return_value=mock_trans)

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session_maker = Mock(return_value=mock_session_ctx)
    service.async_session = mock_session_maker

    # Return the service, the session mock, and the mock_row_object
    # Tests will configure mock_row_object._asdict.return_value
    return service, mock_session, mock_row_object


@pytest.fixture
def mock_user_data():
    """Create mock user data for testing."""
    return UserCreate(email="test@example.com", username="testuser", password="password123")


@pytest.mark.asyncio
async def test_get_user_success(mocked_user_service):
    """Test getting a user by email with mocks."""
    service, mock_session, mock_row_object = mocked_user_service  # Unpack mock_row_object
    mock_user_data_dict = {"email": "test@example.com", "username": "myuser", "hashed_password": "abc123", "is_verified": True}

    # Configure the _asdict method on the mock_row_object
    mock_row_object._asdict = Mock(return_value=mock_user_data_dict)
    # Also, handle the case where user_row itself might be None (user not found)
    # This is done by controlling what result.first() returns initially (mock_row_object or None)
    # For this test, result.first() returns mock_row_object.

    user = await service.get_user("test@example.com")
    assert user is not None
    assert user.email == "test@example.com"
    assert user.username == "myuser"
    assert user.is_verified is True
    mock_session.execute.assert_called_once()
    mock_row_object._asdict.assert_called_once()  # Verify _asdict was called


@pytest.mark.asyncio
async def test_get_nonexistent_user(mocked_user_service):
    """Test retrieving non-existent user with mocks."""
    service, mock_session, mock_row_object_provided_by_fixture = mocked_user_service

    # To simulate user_row being None (user not found), we make result.first() return None.
    # The mock_result_object is what session.execute returns.
    # We need to access it via the session mock to change what its .first() method returns for this specific test.
    mock_session.execute.return_value.first = Mock(return_value=None)

    user = await service.get_user("nonexistent@example.com")
    assert user is None
    mock_session.execute.assert_called_once()
    # mock_row_object_provided_by_fixture._asdict should not have been called
    assert not hasattr(mock_row_object_provided_by_fixture, "_asdict") or not mock_row_object_provided_by_fixture._asdict.called


@pytest.mark.asyncio
async def test_create_user_success(mocked_user_service, mock_user_data):
    """Test successful user creation with mocks."""
    service, mock_session, mock_row_object = mocked_user_service
    hashed_password = "hashed_password_here"
    created_user_data_dict = {
        "email": mock_user_data.email,
        "username": mock_user_data.username,
        "hashed_password": hashed_password,
        "is_verified": False,
    }

    mock_row_object._asdict = Mock(return_value=created_user_data_dict)

    user = await service.create_user(mock_user_data, hashed_password)
    assert isinstance(user, UserInDB)
    assert user.email == mock_user_data.email
    assert user.username == mock_user_data.username
    assert user.hashed_password == hashed_password
    assert user.is_verified is False
    mock_session.execute.assert_called_once()
    mock_row_object._asdict.assert_called_once()
    mock_session.begin().__aenter__.assert_called_once()
    mock_session.begin().__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_create_duplicate_user(mocked_user_service, mock_user_data):
    """Test creating user with duplicate email with mocks."""
    service, mock_session, _ = mocked_user_service
    hashed_password = "hashed_password_here"

    # Configure the execute call to raise SQLAlchemyError for duplicate user
    mock_session.execute.side_effect = SQLAlchemyError("Duplicate user")
    # mock_session.rollback will be called by the service's error handling

    with pytest.raises(SQLAlchemyError, match="Duplicate user"):
        await service.create_user(mock_user_data, hashed_password)

    mock_session.begin().__aexit__.assert_called_once()  # Ensure transaction context was exited


@pytest.mark.asyncio
async def test_create_user_invalid_data():
    """Test user creation Pydantic model validation."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="test@example.com",
            username="",  # Empty username should fail
            password="pass",
        )
    assert "username" in str(exc_info.value).lower()  # check lowercase


@pytest.mark.asyncio
async def test_database_connection_error(mocked_user_service):
    """Test handling of database connection errors with mocks."""
    service, mock_session, _ = mocked_user_service

    mock_session.execute.side_effect = SQLAlchemyError("Connection failed")

    with pytest.raises(SQLAlchemyError, match="Connection failed"):
        await service.get_user("test@example.com")

    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_user_model_validation(mocked_user_service, mock_user_data):
    """Test that returned user data validates against UserInDB model with mocks."""
    service, mock_session, mock_row_object = mocked_user_service
    hashed_password = "hashed_password_here"
    mock_db_user_data_dict = {
        "email": mock_user_data.email,
        "username": mock_user_data.username,
        "hashed_password": hashed_password,
        "is_verified": True,
    }

    mock_row_object._asdict = Mock(return_value=mock_db_user_data_dict)

    user_obj_from_service = await service.create_user(mock_user_data, hashed_password)
    assert isinstance(user_obj_from_service, UserInDB)
    mock_row_object._asdict.assert_called_once()


@pytest.mark.asyncio
async def test_create_user_validation():
    """Test user data Pydantic model validation."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="invalid-email", username="testuser", password="password123")
    assert "email" in str(exc_info.value).lower()

    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="test@example.com", username="", password="password123")
    assert "username" in str(exc_info.value).lower()

    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="test@example.com", username="a" * 51, password="password123")
    assert "username" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_update_password_success(mocked_user_service):
    """Test successful password update with mocks."""
    service, mock_session, _ = mocked_user_service

    # update_password doesn't return, just executes
    await service.update_password("test@example.com", "new_hashed_password")

    mock_session.execute.assert_called_once()
    mock_session.begin().__aenter__.assert_called_once()
    mock_session.begin().__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_db_error(mocked_user_service):
    """Test password update with database error with mocks."""
    service, mock_session, _ = mocked_user_service

    mock_session.execute.side_effect = SQLAlchemyError("DB Error")

    with pytest.raises(SQLAlchemyError, match="DB Error"):
        await service.update_password("test@example.com", "new_hashed_password")

    mock_session.execute.assert_called_once()
    mock_session.begin().__aenter__.assert_called_once()
    mock_session.begin().__aexit__.assert_called_once()  # Transaction context should still exit


# --- Integration Tests (using real test DB via db_session_for_test) ---


@pytest.mark.asyncio
async def test_integration_create_and_get_user(db_engine_with_schema: AsyncEngine, db_session_for_test: AsyncSession):
    """Test creating a new user and retrieving it using the test database."""
    # Pass the test engine
    user_service = UserService(engine=db_engine_with_schema)

    user_data = UserCreate(email="integ_test@example.com", username="integ_user", password="Password12345")
    hashed_password = get_test_password_hash(user_data.password)
    existing_user = await user_service.get_user(user_data.email)
    if existing_user:
        pass
    created_user = await user_service.create_user(user_data, hashed_password)
    assert created_user is not None
    assert created_user.email == user_data.email
    assert created_user.username == user_data.username
    assert created_user.hashed_password == hashed_password
    assert created_user.is_verified is False
    retrieved_user = await user_service.get_user(user_data.email)
    assert retrieved_user is not None
    assert retrieved_user.email == user_data.email
    assert retrieved_user.username == user_data.username
    assert verify_test_password(user_data.password, retrieved_user.hashed_password)
    assert retrieved_user.is_verified is False


@pytest.mark.asyncio
async def test_integration_get_non_existent_user(db_engine_with_schema: AsyncEngine, db_session_for_test: AsyncSession):
    """Test retrieving a non-existent user from the test database."""
    # Pass the test engine
    user_service = UserService(engine=db_engine_with_schema)
    user = await user_service.get_user("no_such_user@example.com")
    assert user is None


@pytest.mark.asyncio
async def test_integration_update_password(db_engine_with_schema: AsyncEngine, db_session_for_test: AsyncSession):
    """Test updating a user's password in the test database."""
    # Pass the test engine
    user_service = UserService(engine=db_engine_with_schema)
    email = "update_pass@example.com"
    username = "update_pass_user"
    old_password_plain = "OldPassword123"
    new_password_plain = "NewPassword456"
    user_to_create = UserCreate(email=email, username=username, password=old_password_plain)
    old_hashed_password = get_test_password_hash(old_password_plain)
    await user_service.create_user(user_to_create, old_hashed_password)
    new_hashed_password = get_test_password_hash(new_password_plain)
    await user_service.update_password(email, new_hashed_password)
    updated_user = await user_service.get_user(email)
    assert updated_user is not None
    assert verify_test_password(new_password_plain, updated_user.hashed_password)
    assert not verify_test_password(old_password_plain, updated_user.hashed_password)


@pytest.mark.asyncio
async def test_integration_mark_user_as_verified(db_engine_with_schema: AsyncEngine, db_session_for_test: AsyncSession):
    """Test marking a user as verified in the test database."""
    # Pass the test engine
    user_service = UserService(engine=db_engine_with_schema)
    email = "verify_user@example.com"
    user_to_create = UserCreate(email=email, username="verify_me", password="Password123")
    hashed_password = get_test_password_hash(user_to_create.password)
    await user_service.create_user(user_to_create, hashed_password)
    user_before_verification = await user_service.get_user(email)
    assert user_before_verification is not None
    assert user_before_verification.is_verified is False
    marked_success = await user_service.mark_user_as_verified(email)
    assert marked_success is True
    user_after_verification = await user_service.get_user(email)
    assert user_after_verification is not None
    assert user_after_verification.is_verified is True


@pytest.mark.asyncio
async def test_integration_verification_token_workflow(db_engine_with_schema: AsyncEngine, db_session_for_test: AsyncSession):
    """Test the full email verification token lifecycle with the test database."""
    from datetime import datetime, timedelta, timezone

    # Pass the test engine
    user_service = UserService(engine=db_engine_with_schema)
    email = "token_user@example.com"
    token_str = "test_verification_token_123"
    user_to_create = UserCreate(email=email, username="token_username", password="TokenPass123")
    hashed_password = get_test_password_hash(user_to_create.password)
    await user_service.create_user(user_to_create, hashed_password)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await user_service.store_email_verification_token(email, token_str, expires_at)
    retrieved_email = await user_service.get_user_email_by_verification_token(token_str)
    assert retrieved_email == email
    await user_service.mark_user_as_verified(email)
    verified_user = await user_service.get_user(email)
    assert verified_user is not None
    assert verified_user.is_verified is True
    await user_service.delete_verification_token(token_str)
    email_after_delete = await user_service.get_user_email_by_verification_token(token_str)
    assert email_after_delete is None
    expired_token_str = "expired_token_456"
    expired_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await user_service.store_email_verification_token(email, expired_token_str, expired_at)
    email_for_expired = await user_service.get_user_email_by_verification_token(expired_token_str)
    assert email_for_expired is None
    await user_service.delete_verification_token(expired_token_str)
