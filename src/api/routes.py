"""API routes for the product search AI."""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from src.ai_agent.product_fetcher import ProductFetcher
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
    """
    return {"message": "Product Search AI API is running!"}


@router.get("/search")
async def search(query: str, auth=Depends(security)):
    """AI-powered product search with authentication."""
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

        fetcher = ProductFetcher()
        search_results = await fetcher.fetch_products(query)

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
