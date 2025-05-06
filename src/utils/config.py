"""Configuration management for environment variables and application settings."""

import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Core configurations
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SERP_API_KEY = os.getenv("SERP_API_KEY")
SERP_API_URL = os.getenv("SERP_API_URL", "https://google.serper.dev/shopping")

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour default cache (e.g., search results)
REDIS_TTL = int(os.getenv("REDIS_TTL", "300"))  # 5 minutes rate limiting
# ADDED: Specific Cache TTLs
CACHE_ENRICHED_PRODUCT_TTL = int(os.getenv("CACHE_ENRICHED_PRODUCT_TTL", "86400"))  # 24 hours for enriched products
CACHE_RANKING_TTL = int(os.getenv("CACHE_RANKING_TTL", "10800"))  # 3 hours for rankings

# Print config (Debug Mode Only)
if DEBUG:
    print(f"✅ Redis Config: {REDIS_HOST}:{REDIS_PORT}, DB={REDIS_DB}, TTL={REDIS_TTL}")

# Security Settings
RATE_LIMIT = {"requests_per_minute": 60, "burst_limit": 10}

# ADDED: API Endpoint Rate Limiting (Example: 5 requests per minute per user)
API_RATE_LIMIT_USER = os.getenv("API_RATE_LIMIT_USER", "5/minute")

# ADDED: Search Agent Settings
SEARCH_INITIAL_FETCH_COUNT = int(os.getenv("SEARCH_INITIAL_FETCH_COUNT", "30"))  # Number of initial products to fetch
SEARCH_ENRICHMENT_COUNT = int(os.getenv("SEARCH_ENRICHMENT_COUNT", "10"))  # Max products to enrich per search
SEARCH_RANKING_LIMIT = int(os.getenv("SEARCH_RANKING_LIMIT", "30"))  # Max products to send for ranking

# ADDED: OpenAI Model Settings
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")  # Default model for general chat/ranking
OPENAI_EXTRACTION_MODEL = os.getenv("OPENAI_EXTRACTION_MODEL", "gpt-4o-mini")  # Model for product detail extraction
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")  # Model for embeddings

# JWT Settings (non-sensitive defaults)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Sensitive values loaded from .env
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY")

# Database Settings
DATABASE_URL = os.getenv("DATABASE_URL")

# ADDED: Enrichment Settings
ENRICHMENT_MAX_PARALLEL = int(os.getenv("ENRICHMENT_MAX_PARALLEL", "5"))
ENRICHMENT_USE_HEADLESS_FALLBACK = os.getenv("ENRICHMENT_USE_HEADLESS_FALLBACK", "False").lower() == "true"
# Optional: Specify endpoint if using a remote browser service like Browserless.io
HEADLESS_BROWSER_ENDPOINT = os.getenv("HEADLESS_BROWSER_ENDPOINT")

# Email Settings
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "noreply@yourdomain.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
IS_DEVELOPMENT = os.getenv("ENVIRONMENT", "development") == "development"
