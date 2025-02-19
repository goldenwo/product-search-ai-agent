"""User models for authentication."""

from pydantic import BaseModel, EmailStr


class UserLogin(BaseModel):
    """Login request model."""

    email: EmailStr
    password: str


class UserCreate(BaseModel):
    """User registration model."""

    email: EmailStr
    username: str
    password: str


class UserInDB(BaseModel):
    """Internal user model with hashed password."""

    email: EmailStr
    username: str
    hashed_password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
