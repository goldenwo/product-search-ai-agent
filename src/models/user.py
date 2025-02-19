"""Pydantic models for user authentication and data validation."""

from pydantic import BaseModel, EmailStr


class UserLogin(BaseModel):
    """
    Login request model with email and password.

    Attributes:
        email: User's email address
        password: Plain text password
    """

    email: EmailStr
    password: str


class UserCreate(BaseModel):
    """
    User registration model with full user details.

    Attributes:
        email: User's email address
        username: Chosen username
        password: Plain text password
    """

    email: EmailStr
    username: str
    password: str


class UserInDB(BaseModel):
    """
    Internal database model with hashed password.

    Attributes:
        email: User's email address
        username: User's username
        hashed_password: Bcrypt hashed password
    """

    email: EmailStr
    username: str
    hashed_password: str

    class Config:
        """
        Configuration for Pydantic model.

        Allows conversion from SQLAlchemy model.
        """

        from_attributes = True  # Allows conversion from SQLAlchemy model


class Token(BaseModel):
    """
    Token model with access and refresh tokens.

    Attributes:
        access_token: JWT access token
        refresh_token: JWT refresh token
        token_type: Token type (default is "bearer")
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User data returned to client."""

    email: EmailStr
    username: str
