"""Configuration management for environment variables and application settings."""

import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_env_int(var_name: str, default: str) -> int:
    value_str = os.getenv(var_name, default)
    # Attempt to strip comments and whitespace before int conversion
    if "#" in value_str:
        value_str = value_str.split("#", 1)[0]
    return int(value_str.strip())


def get_env_bool(var_name: str, default: str) -> bool:
    value_str = os.getenv(var_name, default)
    # Attempt to strip comments and whitespace before bool conversion
    if "#" in value_str:
        value_str = value_str.split("#", 1)[0]
    return value_str.strip().lower() == "true"


# Core configurations
DEBUG = get_env_bool("DEBUG", "False")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SERP_API_KEY = os.getenv("SERP_API_KEY")
SERP_API_URL = os.getenv("SERP_API_URL", "https://google.serper.dev/shopping")

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = get_env_int("REDIS_PORT", "6379")
REDIS_DB = get_env_int("REDIS_DB", "0")
CACHE_TTL = get_env_int("CACHE_TTL", "3600")  # Default cache TTL (e.g., search results)
REDIS_TTL = get_env_int("REDIS_TTL", "300")  # Rate limiting TTL
# Specific Cache TTLs
CACHE_ENRICHED_PRODUCT_TTL = get_env_int("CACHE_ENRICHED_PRODUCT_TTL", "86400")  # 24 hours for enriched products
CACHE_RANKING_TTL = get_env_int("CACHE_RANKING_TTL", "10800")  # 3 hours for rankings
CACHE_SEARCH_RESULTS_TTL = get_env_int("CACHE_SEARCH_RESULTS_TTL", "3600")  # 1 hour for final search results (used in routes)

# Optional: Print config only in debug mode for verification
if DEBUG:
    print(f"✅ Redis Config: {REDIS_HOST}:{REDIS_PORT}, DB={REDIS_DB}, TTL={REDIS_TTL}")

# Security Settings
# Global rate limit settings (can be overridden per endpoint)
# RATE_LIMIT = {"requests_per_minute": 60, "burst_limit": 10} # This is not used directly as int/bool, string is fine

# Rate limit specifically for authenticated user actions (e.g., search)
API_RATE_LIMIT_USER = os.getenv("API_RATE_LIMIT_USER", "5/minute")  # String, not int/bool

# Search Agent Settings
SEARCH_INITIAL_FETCH_COUNT = get_env_int("SEARCH_INITIAL_FETCH_COUNT", "30")  # How many products to fetch initially from SERP
SEARCH_ENRICHMENT_COUNT = get_env_int("SEARCH_ENRICHMENT_COUNT", "10")  # How many top products to enrich with details
SEARCH_RANKING_LIMIT = get_env_int("SEARCH_RANKING_LIMIT", "30")  # How many products to send to the AI for ranking

# OpenAI Model Settings
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")  # Default model for ranking and general tasks
OPENAI_EXTRACTION_MODEL = os.getenv("OPENAI_EXTRACTION_MODEL", "gpt-4o-mini")  # Model used specifically for product detail extraction (JSON mode)
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")  # Model for creating text embeddings

# JWT Settings
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = get_env_int("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
REFRESH_TOKEN_EXPIRE_DAYS = get_env_int("REFRESH_TOKEN_EXPIRE_DAYS", "7")

# Sensitive values loaded from .env (ensure .env file exists and is populated)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY")

# Database Settings
DATABASE_URL = os.getenv("DATABASE_URL")

# Enrichment Settings
ENRICHMENT_MAX_PARALLEL = get_env_int("ENRICHMENT_MAX_PARALLEL", "5")  # Max concurrent enrichment tasks
ENRICHMENT_USE_HEADLESS_FALLBACK = get_env_bool("ENRICHMENT_USE_HEADLESS_FALLBACK", "False")  # Use Playwright if direct fetch fails
# Optional: Specify endpoint if using a remote browser service (e.g., Browserless.io)
HEADLESS_BROWSER_ENDPOINT = os.getenv("HEADLESS_BROWSER_ENDPOINT")

# Email Settings
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "noreply@yourdomain.com")  # Default sender address
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")  # Base URL for frontend links (e.g., password reset)
# For IS_DEVELOPMENT, we need to be careful with default for get_env_bool if ENVIRONMENT is not set.
# If ENVIRONMENT variable might be missing, a more direct check is os.getenv("ENVIRONMENT", "development") == "development"
IS_DEVELOPMENT = os.getenv("ENVIRONMENT", "development").strip().lower() == "development"

# Token Expiry Settings
VERIFICATION_TOKEN_EXPIRE_HOURS = get_env_int("VERIFICATION_TOKEN_EXPIRE_HOURS", "24")  # For email verification
