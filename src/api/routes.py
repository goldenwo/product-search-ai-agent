"""API routes for AI-powered product search with authentication."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.ai_agent.search_agent import SearchAgent
from src.dependencies import get_auth_service, get_redis_service, get_search_agent, limiter
from src.services.auth_service import AuthService
from src.services.redis_service import RedisService
from src.utils import OpenAIServiceError, SerpAPIException, logger
from src.utils.config import API_RATE_LIMIT_USER

router = APIRouter()
security = HTTPBearer()


# Simplified key function for demonstration - relies on IP.
# Per-user limiting requires passing auth_service or user identifier to key_func.
# slowapi doesn't easily support async key_funcs or Depends within key_funcs.
# Consider alternative rate-limiting libraries or strategies for per-user limits.
# Key Function (Using IP for now)
def key_func_ip_only(request: Request) -> str:
    logger.warning("Using IP-based rate limiting for /search route.")  # Log the limitation
    return get_remote_address(request)


@router.get("/")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """
    Health check endpoint to verify API status.

    Returns:
        dict: Status message indicating API is running
    """
    return {"message": "Product Search AI API is running!"}


@router.get("/search")
@limiter.limit(API_RATE_LIMIT_USER, key_func=key_func_ip_only)
async def search(
    request: Request,
    query: str,
    auth: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
    redis_cache: RedisService = Depends(get_redis_service),
    search_agent: SearchAgent = Depends(get_search_agent),
):
    """
    AI-powered product search with authentication and caching.

    Args:
        request: FastAPI request object (used by rate limiter)
        query: Search query string
        auth: JWT bearer token for authentication

    Returns:
        dict: Search results with metadata

    Raises:
        HTTPException: 401 (Auth), 400 (Bad Query), 429 (Rate Limit), 500/503 (Service Error)
    """
    email = ""
    try:
        # Verify token using the injected auth_service
        email = auth_service.verify_token(auth.credentials)
        logger.info(f"Authenticated search request for user: {email}")
    except HTTPException as exc:
        logger.warning(f"Search authentication failed: {exc.detail}")
        raise

    # Sanitize input
    query = re.sub(r"[<>]", "", query.strip())
    if not query:
        return {"error": "Empty search query"}

    if len(query) > 500:
        return {"error": "Query too long (max 500 characters)"}

    # --- Wrapped main logic in try/except for better error scoping ---
    try:
        # Use injected redis_cache
        cache_key = f"search:{email}:{query.lower()}"
        cached_results = None
        try:
            cached_results = await redis_cache.get_cache(cache_key)
        except Exception as redis_err:
            logger.error(f"⚠️ Redis cache GET error for key '{cache_key}' (User: {email}): {redis_err}. Proceeding without cache.")

        if cached_results:
            logger.info(f"Cache hit for search query: '{query}'. User: {email}")
            return {"query": query, "cached": True, "results": cached_results, "user": email}
        else:
            logger.info(f"Cache miss for search query: '{query}'. User: {email}. Processing request.")

        # Use the injected search_agent instance
        products = await search_agent.search(query, top_n=10)

        search_results = [product.to_json() for product in products]

        if not search_results:
            logger.info(f"No products found for query: '{query}'. User: {email}")
            return {"query": query, "results": [], "message": "No products found", "user": email}

        try:
            # Use injected redis_cache
            await redis_cache.set_cache(cache_key, search_results)
            logger.info(f"Cached search results for key: '{cache_key}'. User: {email}")
        except Exception as redis_err:
            logger.error(f"⚠️ Redis cache SET error for key '{cache_key}' (User: {email}): {redis_err}. Results returned but not cached.")

        return {"query": query, "cached": False, "results": search_results, "user": email}

    # --- Specific Error Handling ---
    except RateLimitExceeded as e:
        # Logged automatically by slowapi's handler usually, but good to note
        logger.warning(f"Rate limit exceeded for user {email}. Detail: {e.detail}")
        # Re-raise standard HTTPException
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Rate limit exceeded: {e.detail}")
    except (OpenAIServiceError, SerpAPIException) as e:
        logger.error(f"❌ Service error during search for query '{query}', User '{email}': {str(e)}")
        # Use status code from the exception if available, default to 503 Service Unavailable
        status_code = getattr(e, "status_code", 503)
        raise HTTPException(status_code=status_code, detail="Service temporarily unavailable, please try again later.")
    except ValueError as e:
        # Catch specific ValueErrors potentially raised by deeper logic (e.g., parsing)
        logger.error(f"❌ Invalid data encountered during search for query '{query}', User '{email}': {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid data encountered during search.")
    except Exception as e:
        # Catch-all for unexpected errors during the search agent's processing
        logger.exception(f"💥 Unexpected internal error during search for query '{query}', User '{email}': {str(e)}")
        raise HTTPException(status_code=500, detail="An internal server error occurred processing your request.")
