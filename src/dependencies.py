"""Shared application dependencies."""

# Caching and Rate Limiting
from fastapi import Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.ai_agent.search_agent import SearchAgent

# Core Services
from src.services.auth_service import AuthService
from src.services.openai_service import OpenAIService
from src.services.product_enricher import ProductEnricher
from src.services.redis_service import RedisService
from src.services.serp_service import SerpService
from src.utils import logger
from src.utils.config import OPENAI_API_KEY, REDIS_DB, REDIS_HOST, REDIS_PORT  # Added OpenAI Key

# --- Cached Singleton Instances ---
# Use a simple dictionary to cache instances within the application lifecycle
# Note: For request-scoped instances, FastAPI's Depends handles caching implicitly.
# This is more for ensuring only one instance of potentially heavy services exists.
_cache = {}


def get_redis_service() -> RedisService:
    """Dependency function to get a RedisService instance."""
    if "redis" not in _cache:
        # Assuming RedisService doesn't need async connection passed here,
        # modify if it requires specific connection setup.
        _cache["redis"] = RedisService()
    return _cache["redis"]


def get_openai_service() -> OpenAIService:
    """Dependency function to get an OpenAIService instance."""
    if "openai" not in _cache:
        # Pass API key if needed, though service might load from env itself
        _cache["openai"] = OpenAIService(api_key=OPENAI_API_KEY)
    return _cache["openai"]


def get_product_enricher(openai_service: OpenAIService = Depends(get_openai_service)) -> ProductEnricher:
    """Dependency function to get a ProductEnricher instance."""
    # ProductEnricher depends on OpenAIService
    if "enricher" not in _cache:
        # Inject the dependency
        _cache["enricher"] = ProductEnricher(openai_service=openai_service)
    return _cache["enricher"]


def get_serp_service() -> SerpService:
    """Dependency function to get a SerpService instance."""
    # Assumes SerpService loads keys/URLs from config/env internally
    if "serp" not in _cache:
        # Use factory method if preferred, or direct instantiation
        # from src.services.factory import SerpServiceFactory, SerpProvider
        # _cache["serp"] = SerpServiceFactory.create(provider=SerpProvider.SERPER)
        _cache["serp"] = SerpService()
    return _cache["serp"]


def get_search_agent(
    redis_cache: RedisService = Depends(get_redis_service),
    # Inject other dependencies SearchAgent needs directly
    openai_service: OpenAIService = Depends(get_openai_service),
    serp_service: SerpService = Depends(get_serp_service),
    product_enricher: ProductEnricher = Depends(get_product_enricher),
) -> SearchAgent:
    """Dependency function to create a SearchAgent with its dependencies."""
    # SearchAgent instantiation now happens here, ensuring dependencies are managed.
    # Note: This creates a *new* agent per request using Depends.
    # If you need a singleton agent, manage its instance in _cache like other services.
    # For now, let's assume per-request is fine.

    # We need to modify SearchAgent.__init__ to accept these dependencies.
    return SearchAgent(redis_cache=redis_cache, openai_service=openai_service, serp_service=serp_service, product_enricher=product_enricher)


def get_auth_service() -> AuthService:
    """Dependency function to get an AuthService instance."""
    # AuthService might depend on UserService, EmailService, RateLimitService
    # These dependencies would also need to be managed here or injected.
    # For simplicity now, assume AuthService handles its own internal setup.
    if "auth" not in _cache:
        _cache["auth"] = AuthService()
    return _cache["auth"]


# --- Rate Limiter Key Function ---
def key_func_user_or_ip(request: Request) -> str:
    """
    Generates a rate limit key based on authenticated user email if available,
    otherwise falls back to the client's IP address.
    Requires an upstream authentication middleware to set request.state.user_email.
    """
    # Attempt to get user identifier set by authentication middleware
    # Adjust "user_email" if your middleware uses a different state attribute name
    user_identifier = getattr(request.state, "user_email", None)

    if user_identifier:
        # Use a user-specific key format
        key = f"user:{user_identifier}"
        # logger.debug(f"Rate limiting key (User): {key}") # Optional: debug logging
        return key
    else:
        # Fallback to IP address if no user identifier is found in state
        ip = get_remote_address(request)
        key = f"ip:{ip}"
        # Log this fallback case, as it might indicate an issue or an intended public endpoint
        # Check if request.url exists and has path before logging
        path_info = request.url.path if hasattr(request, "url") and hasattr(request.url, "path") else "unknown path"
        logger.warning(f"Rate limiting key (Fallback to IP): {key} for path {path_info}")
        return key


# --- Rate Limiter Instance --- (Keep as is)
limiter = Limiter(
    key_func=get_remote_address,  # NOTE: Default key_func, route overrides where needed
    storage_uri=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
    strategy="fixed-window",
    default_limits=["1000/minute"],
)

# You can add other shared dependencies here later, e.g.:
# def get_db_session(): ...
# def get_settings(): ...
