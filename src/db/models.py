"""Database models for SQLAlchemy."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
)

from src.schemas.base import Base


class User(Base):
    """Database model for user table."""

    __tablename__ = "users"
    email = Column(String, primary_key=True, index=True)
    username = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)


class EmailVerificationToken(Base):
    """Database model for email_verification_tokens table."""

    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_email = Column(String, ForeignKey("users.email", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Product(Base):
    """Database model for the products table."""

    __tablename__ = "products"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    store = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=True, index=True)
    brand = Column(String, nullable=True, index=True)
    image_url = Column(String, nullable=True)
    relevance_score = Column(Float, nullable=True)
    relevance_explanation = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    shipping = Column(String, nullable=True)
    offers = Column(String, nullable=True)
    position = Column(Integer, nullable=True)
    source = Column(String, nullable=True)
    specifications = Column(JSON, nullable=True)
