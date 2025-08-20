"""Pydantic models for user authentication and data validation."""

from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints
from pydantic.config import ConfigDict


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
        username: Chosen username (non-empty string, 1-50 chars)
        password: Plain text password
    """

    email: EmailStr
    username: Annotated[str, StringConstraints(min_length=1, max_length=50, strip_whitespace=True)]
    password: str


class UserInDB(BaseModel):
    """
    Internal database model with hashed password.

    Attributes:
        email: User's email address
        username: User's username
        hashed_password: Bcrypt hashed password
        is_verified: Indicates whether the user's email is verified
    """

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr
    username: str
    hashed_password: str
    is_verified: bool = False


class Token(BaseModel):
    """
    Token model with access and refresh tokens.

    Attributes:
        access_token: JWT access token
        refresh_token: JWT refresh token
        token_type: Token type (default is "bearer")
    """

    model_config = ConfigDict(json_schema_extra={"example": {"access_token": "eyJ0...", "refresh_token": "eyJ1...", "token_type": "bearer"}})

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User data returned to client."""

    email: EmailStr
    username: str
