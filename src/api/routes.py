"""API routes for AI-powered product search with authentication."""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from src.ai_agent.search_agent import SearchAgent
from src.services.auth_service import AuthService
from src.services.redis_service import RedisService
from src.utils import FAISSIndexError, OpenAIServiceError, StoreAPIError, logger

router = APIRouter()
redis_cache = RedisService()
auth_service = AuthService()
security = HTTPBearer()


@router.get("/")
def health_check():
    """
    Health check endpoint to verify API status.

    Returns:
        dict: Status message indicating API is running
    """
    return {"message": "Product Search AI API is running!"}


@router.get("/search")
async def search(query: str, auth=Depends(security)):
    """
    AI-powered product search with authentication and caching.

    Args:
        query: Search query string
        auth: JWT bearer token for authentication

    Returns:
        dict: Search results with metadata
            - query: Original search query
            - cached: Whether results came from cache
            - results: List of matched products
            - user: Email of authenticated user

    Raises:
        HTTPException:
            - 401: Invalid authentication token
            - 400: Invalid search query
        OpenAIServiceError: If AI service fails
        FAISSIndexError: If vector search fails
        StoreAPIError: If store API calls fail
    """
    # Verify token and get user
    try:
        email = auth_service.verify_token(auth.credentials)
    except HTTPException as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    # Sanitize input
    query = re.sub(r"[<>]", "", query.strip())
    if not query:
        return {"error": "Empty search query"}

    if len(query) > 500:
        return {"error": "Query too long (max 500 characters)"}

    try:
        # Add user-specific cache key
        cache_key = f"search:{email}:{query.lower()}"
        cached_results = await redis_cache.get_cache(cache_key)
        if cached_results:
            return {"query": query, "cached": True, "results": cached_results}

        # Pass the existing redis_cache to SearchAgent
        search_agent = SearchAgent(redis_cache=redis_cache)
        # Get top 10 products by default
        products = await search_agent.search(query, top_n=10)

        # Convert Product objects to dictionaries for JSON serialization
        search_results = [product.to_json() for product in products]

        if not search_results:
            return {"query": query, "results": [], "message": "No products found"}

        await redis_cache.set_cache(cache_key, search_results)
        return {"query": query, "cached": False, "results": search_results, "user": email}

    except (OpenAIServiceError, FAISSIndexError, StoreAPIError) as e:
        logger.error("❌ Search error: %s", str(e))
        return {"error": "Unable to complete your search at this time."}
    except ValueError as e:
        logger.error("❌ Invalid input: %s", str(e))
        return {"error": "Invalid search parameters"}
