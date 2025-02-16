"""Configuration management module for environment variables and application settings."""

import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Core configurations
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
FAISS_VECTOR_DIMENSION = int(os.getenv("FAISS_VECTOR_DIMENSION", "128"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Store API URLs - dynamically loaded from environment
def get_store_api_url(store_name: str) -> str:
    """Get store API URL from environment with fallback to empty string."""
    return os.getenv(f"{store_name.upper()}_API_URL", "")


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
