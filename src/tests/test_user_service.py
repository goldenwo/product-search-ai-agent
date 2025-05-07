"""Test the UserService class."""

from unittest.mock import AsyncMock, Mock

from pydantic import ValidationError
import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.models.user import UserCreate, UserInDB
from src.services.user_service import UserService


@pytest.fixture
def user_service():
    """Create UserService instance with mocked database."""
    service = UserService()

    # Create mock session
    mock_session = AsyncMock()
    mock_session.execute.return_value = Mock(first=Mock())
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    # Mock the transaction context manager
    mock_trans = AsyncMock()
    mock_trans.__aenter__ = AsyncMock(return_value=mock_session)
    mock_trans.__aexit__ = AsyncMock(return_value=False)  # Return False to propagate errors
    mock_session.begin = Mock(return_value=mock_trans)

    # Mock the session maker context manager
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)  # Return False to propagate errors

    # Create session maker that returns the session context
    mock_session_maker = Mock(return_value=mock_session_ctx)
    service.async_session = mock_session_maker

    return service, mock_session


@pytest.fixture
def mock_user_data():
    """Create mock user data for testing."""
    return UserCreate(email="test@example.com", username="testuser", password="password123")


@pytest.mark.asyncio
async def test_get_user_success(user_service):  # pylint: disable=redefined-outer-name
    """Test getting a user by email."""
    service, mock_session = user_service
    mock_session.execute.return_value.first.return_value = {"email": "test@example.com", "username": "myuser", "hashed_password": "abc123"}

    user = await service.get_user("test@example.com")
    assert user is not None


@pytest.mark.asyncio
async def test_get_nonexistent_user(user_service):  # pylint: disable=redefined-outer-name
    """Test retrieving non-existent user."""
    service, mock_session = user_service
    mock_session.execute.return_value.first.return_value = None

    user = await service.get_user("nonexistent@example.com")
    assert user is None


@pytest.mark.asyncio
async def test_create_user_success(user_service, mock_user_data):  # pylint: disable=redefined-outer-name
    """Test successful user creation."""
    hashed_password = "hashed_password_here"

    # Create a Row-like object that SQLAlchemy would return
    class MockRow:
        """Mock Row object for testing."""

        def __init__(self, data):
            self.__dict__.update(data)

        def __getitem__(self, key):
            return self.__dict__[key]

    mock_db_user = MockRow({"email": mock_user_data.email, "username": mock_user_data.username, "hashed_password": hashed_password})

    service, mock_session = user_service
    mock_session.execute.return_value.first.return_value = mock_db_user

    user = await service.create_user(mock_user_data, hashed_password)
    assert isinstance(user, UserInDB)
    assert user.email == mock_user_data.email
    assert user.username == mock_user_data.username
    assert user.hashed_password == hashed_password


@pytest.mark.asyncio
async def test_create_duplicate_user(user_service, mock_user_data):  # pylint: disable=redefined-outer-name
    """Test creating user with duplicate email."""
    service, mock_session = user_service

    # Configure the execute call to raise the exception
    mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("Duplicate user"))
    mock_session.rollback = AsyncMock()

    # Mock the transaction context manager
    mock_trans = AsyncMock()
    mock_trans.__aenter__ = AsyncMock(return_value=mock_session)
    mock_trans.__aexit__ = AsyncMock(return_value=False)  # Return False to propagate error
    mock_session.begin = Mock(return_value=mock_trans)

    # Mock the session maker context manager
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)  # Return False to propagate error

    # Create session maker that returns the session context
    mock_session_maker = Mock(return_value=mock_session_ctx)
    service.async_session = mock_session_maker

    with pytest.raises(SQLAlchemyError):
        await service.create_user(mock_user_data, "hashed_password")


@pytest.mark.asyncio
async def test_create_user_invalid_data(user_service):  # pylint: disable=redefined-outer-name
    """Test user creation with invalid data."""
    # Test that invalid username raises validation error
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="test@example.com",
            username="",  # Empty username should fail
            password="pass",
        )
    assert "username" in str(exc_info.value)
    assert "at least 1 character" in str(exc_info.value)


@pytest.mark.asyncio
async def test_database_connection_error(user_service):  # pylint: disable=redefined-outer-name
    """Test handling of database connection errors."""
    service, mock_session = user_service

    # Configure the execute call to raise the exception
    mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("Connection failed"))

    # Mock the session maker context manager
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)  # Return False to propagate error

    # Create session maker that returns the session context
    mock_session_maker = Mock(return_value=mock_session_ctx)
    service.async_session = mock_session_maker

    with pytest.raises(SQLAlchemyError):
        await service.get_user("test@example.com")


@pytest.mark.asyncio
async def test_user_model_validation(user_service, mock_user_data):  # pylint: disable=redefined-outer-name
    """Test that returned user data validates against UserInDB model."""
    hashed_password = "hashed_password_here"

    mock_db_user = {"email": mock_user_data.email, "username": mock_user_data.username, "hashed_password": hashed_password}

    service, mock_session = user_service
    mock_session.execute.return_value.first.return_value = mock_db_user

    user = await service.create_user(mock_user_data, hashed_password)
    UserInDB.model_validate(user)  # Should not raise validation error


@pytest.mark.asyncio
async def test_create_user_validation():
    """Test user data validation."""
    # Test invalid email
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="invalid-email", username="testuser", password="password123")
    assert "email" in str(exc_info.value)  # Verify it's the email validation that failed

    # Test invalid username (too short)
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="test@example.com",
            username="",  # Empty username
            password="password123",
        )
    assert "username" in str(exc_info.value)  # Verify it's the username validation that failed

    # Test invalid username (too long)
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="test@example.com",
            username="a" * 51,  # Username too long
            password="password123",
        )
    assert "username" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_password_success(user_service):  # pylint: disable=redefined-outer-name
    """Test successful password update."""
    service, mock_session = user_service
    mock_session.execute = AsyncMock()

    await service.update_password("test@example.com", "new_hashed_password")
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_db_error(user_service):  # pylint: disable=redefined-outer-name
    """Test password update with database error."""
    service, mock_session = user_service

    # Configure the execute call to raise the exception
    mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("DB Error"))
    mock_session.rollback = AsyncMock()

    # Mock the transaction context manager
    mock_trans = AsyncMock()
    mock_trans.__aenter__ = AsyncMock(return_value=mock_session)
    mock_trans.__aexit__ = AsyncMock(return_value=False)  # Return False to propagate error
    mock_session.begin = Mock(return_value=mock_trans)

    # Mock the session maker context manager
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)  # Return False to propagate error

    # Create session maker that returns the session context
    mock_session_maker = Mock(return_value=mock_session_ctx)
    service.async_session = mock_session_maker

    with pytest.raises(SQLAlchemyError):
        await service.update_password("test@example.com", "new_hashed_password")
    mock_session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_create_and_get_user(user_service: UserService, db_session_for_test):
    """Test creating a new user and retrieving it."""
    user_data = UserCreate(email="test@example.com", username="testuser", password="Password123")
    hashed_password = "hashed_test_password"  # In real tests, you might hash it or mock hashing

    created_user = await user_service.create_user(user_data, hashed_password)
    assert created_user is not None
    assert created_user.email == user_data.email
    assert created_user.username == user_data.username
    assert created_user.hashed_password == hashed_password
    assert created_user.is_verified is False  # Default from schema/model

    retrieved_user = await user_service.get_user(user_data.email)
    assert retrieved_user is not None
    assert retrieved_user.email == created_user.email
    assert retrieved_user.username == created_user.username
    assert retrieved_user.is_verified == created_user.is_verified


@pytest.mark.asyncio
async def test_get_non_existent_user(user_service: UserService, db_session_for_test):
    """Test retrieving a non-existent user."""
    user = await user_service.get_user("nonexistent@example.com")
    assert user is None


@pytest.mark.asyncio
async def test_update_password(user_service: UserService, db_session_for_test):
    """Test updating a user's password."""
    # First, create a user to update
    user_data = UserCreate(email="update@example.com", username="updateuser", password="OldPassword1")
    initial_hashed_password = "initial_hashed_password"
    await user_service.create_user(user_data, initial_hashed_password)

    new_hashed_password = "new_hashed_password"
    await user_service.update_password(user_data.email, new_hashed_password)

    updated_user = await user_service.get_user(user_data.email)
    assert updated_user is not None
    assert updated_user.hashed_password == new_hashed_password


@pytest.mark.asyncio
async def test_mark_user_as_verified(user_service: UserService, db_session_for_test):
    """Test marking a user as verified."""
    user_data = UserCreate(email="verify@example.com", username="verifyuser", password="Password123")
    await user_service.create_user(user_data, "hashed_password")

    success = await user_service.mark_user_as_verified(user_data.email)
    assert success is True

    verified_user = await user_service.get_user(user_data.email)
    assert verified_user is not None
    assert verified_user.is_verified is True


@pytest.mark.asyncio
async def test_verification_token_workflow(user_service: UserService, db_session_for_test):
    """Test storing, retrieving, and deleting email verification tokens."""
    from datetime import datetime, timedelta, timezone

    user_email = "token_user@example.com"
    # Create the user first
    user_data = UserCreate(email=user_email, username="tokenuser", password="Password123")
    await user_service.create_user(user_data, "hashed_password_for_token_user")

    token = "test_verification_token_123"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    await user_service.store_email_verification_token(user_email, token, expires_at)

    retrieved_email = await user_service.get_user_email_by_verification_token(token)
    assert retrieved_email == user_email

    # Test with expired token
    expired_token = "expired_token_456"
    expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
    await user_service.store_email_verification_token(user_email, expired_token, expired_time)
    retrieved_expired_email = await user_service.get_user_email_by_verification_token(expired_token)
    assert retrieved_expired_email is None

    await user_service.delete_verification_token(token)
    retrieved_email_after_delete = await user_service.get_user_email_by_verification_token(token)
    assert retrieved_email_after_delete is None


# Add more tests for edge cases, error handling (e.g., IntegrityError for duplicate emails if applicable based on DB schema)
# and other UserService methods.
