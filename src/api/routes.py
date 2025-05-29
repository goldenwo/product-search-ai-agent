"""API routes for AI-powered product search with authentication."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import redis
from slowapi.errors import RateLimitExceeded

from src.ai_agent.search_agent import SearchAgent
from src.dependencies import get_auth_service, get_redis_service, get_search_agent, key_func_user_or_ip, limiter
from src.services.auth_service import AuthService
from src.services.redis_service import RedisService
from src.utils import OpenAIServiceError, SerpAPIException, logger
from src.utils.config import API_RATE_LIMIT_USER, CACHE_SEARCH_RESULTS_TTL

router = APIRouter()
security = HTTPBearer()


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
@limiter.limit(API_RATE_LIMIT_USER, key_func=key_func_user_or_ip)
async def search(
    request: Request,
    query: str,
    auth: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
    redis_cache: RedisService = Depends(get_redis_service),
    search_agent: SearchAgent = Depends(get_search_agent),
):
    """
    AI-powered product search endpoint.

    Requires authentication. Performs search, enrichment, and ranking.
    Handles caching of final search results.

    Args:
        request: FastAPI request object (used by rate limiter).
        query: Search query string
        auth: JWT bearer token for authentication

    Returns:
        dict: Search results with metadata

    Raises:
        HTTPException: 401 (Auth), 400 (Bad Query), 429 (Rate Limit), 500/503 (Service Error)
    """
    email = ""
    try:
        # Verify JWT token and get user email
        email = auth_service.verify_token(auth.credentials)
        logger.info("Authenticated search request for user: %s", email)
    except HTTPException as exc:
        logger.warning("Search authentication failed: %s", exc.detail)
        raise

    # Sanitize input
    query = re.sub(r"[<>]", "", query.strip())
    if not query:
        return {"error": "Empty search query"}

    if len(query) > 500:
        return {"error": "Query too long (max 500 characters)"}

    # --- Search Logic with Caching ---
    try:
        # Use user-specific cache key for search results
        cache_key = f"search:{email}:{query.lower()}"
        cached_results = None
        try:
            cached_results = await redis_cache.get_cache(cache_key)
        except redis.RedisError as redis_err:
            # Log Redis error but proceed without cache
            logger.error("⚠️ Redis cache GET error for key '%s' (User: %s): %s. Proceeding without cache.", cache_key, email, redis_err)
        except Exception as e:
            logger.error("❌ Unexpected error during cache GET for key '%s' (User: %s): %s. Proceeding without cache.", cache_key, email, e)

        if cached_results:
            logger.info("Cache hit for search query: '%s'. User: %s", query, email)
            return {"query": query, "cached": True, "results": cached_results, "user": email}
        else:
            logger.info("Cache miss for search query: '%s'. User: %s. Processing request.", query, email)

        # Execute the core search logic via the agent
        products = await search_agent.search(query, top_n=10)

        search_results = [product.to_json() for product in products]

        if not search_results:
            logger.info("No products found for query: '%s'. User: %s", query, email)
            return {"query": query, "results": [], "message": "No products found", "user": email}

        # Cache the results
        try:
            await redis_cache.set_cache(cache_key, search_results, ttl=CACHE_SEARCH_RESULTS_TTL)
            logger.info("Cached search results for key: '%s' (TTL: %ds). User: %s", cache_key, CACHE_SEARCH_RESULTS_TTL, email)
        except redis.RedisError as redis_err:
            # Log Redis error but return results anyway
            logger.error("⚠️ Redis cache SET error for key '%s' (User: %s): %s. Results returned but not cached.", cache_key, email, redis_err)
        except Exception as e:
            logger.error("❌ Unexpected error during cache SET for key '%s' (User: %s): %s. Results returned but not cached.", cache_key, email, e)

        return {"query": query, "cached": False, "results": search_results, "user": email}

    # --- Error Handling ---
    except RateLimitExceeded as e:
        logger.warning("Rate limit exceeded for user %s. Detail: %s", email, e.detail)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Rate limit exceeded: {e.detail}")
    except (OpenAIServiceError, SerpAPIException) as e:
        logger.error("❌ Service error during search for query '%s', User '%s': %s", query, email, e)
        # Use status code from the custom exception if available, default to 503
        status_code = getattr(e, "status_code", 503)
        raise HTTPException(status_code=status_code, detail="Service temporarily unavailable, please try again later.")
    except ValueError as e:
        logger.error("❌ Invalid data encountered during search for query '%s', User '%s': %s", query, email, e)
        raise HTTPException(status_code=400, detail="Invalid data encountered during search.")
    except Exception as e:
        logger.exception("💥 Unexpected internal error during search for query '%s', User '%s': %s", query, email, e)
        raise HTTPException(status_code=500, detail="An internal server error occurred processing your request.")
