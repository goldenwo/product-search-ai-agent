"""Configuration management module for environment variables and application settings."""

import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Core configurations
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
FAISS_VECTOR_DIMENSION = int(os.getenv("FAISS_VECTOR_DIMENSION", "128"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def get_store_api_url(store_name: str, default_url: Optional[str] = None) -> str:
    """
    Get store API URL with fallback chain:
    1. Environment variable
    2. Provided default URL
    3. Empty string
    """
    return os.getenv(f"{store_name.upper()}_API_URL", "") or default_url or ""


def get_store_api_key(store_name: str) -> str:
    """Get store API key from environment with fallback to empty string."""
    return os.getenv(f"{store_name.upper()}_API_KEY", "")


# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_TTL = int(os.getenv("REDIS_TTL", "300"))  # Cache timeout (default: 300 seconds)

# Print config (Debug Mode Only)
if DEBUG:
    print(f"✅ Loaded Config: FAISS_VECTOR_DIMENSION={FAISS_VECTOR_DIMENSION}, DEBUG={DEBUG}")
    print(f"✅ Redis Config: {REDIS_HOST}:{REDIS_PORT}, DB={REDIS_DB}, TTL={REDIS_TTL}")

# Security Settings
RATE_LIMIT = {"requests_per_minute": 60, "burst_limit": 10}

# JWT Settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Database Settings
DATABASE_URL = os.getenv("DATABASE_URL")
