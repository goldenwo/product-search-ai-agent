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
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour search results cache
REDIS_TTL = int(os.getenv("REDIS_TTL", "300"))  # 5 minutes rate limiting

# Print config (Debug Mode Only)
if DEBUG:
    print(f"✅ Redis Config: {REDIS_HOST}:{REDIS_PORT}, DB={REDIS_DB}, TTL={REDIS_TTL}")

# Security Settings
RATE_LIMIT = {"requests_per_minute": 60, "burst_limit": 10}

# JWT Settings (non-sensitive defaults)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Sensitive values loaded from .env
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY")

# Database Settings
DATABASE_URL = os.getenv("DATABASE_URL")

# Email Settings
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "noreply@yourdomain.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
IS_DEVELOPMENT = os.getenv("ENVIRONMENT", "development") == "development"
