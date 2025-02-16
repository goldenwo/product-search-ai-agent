from fastapi import APIRouter, Depends

from src.ai_agent.product_fetcher import ProductFetcher
from src.api.dependencies import get_store_apis
from src.services.redis_service import RedisService

router = APIRouter()
redis_cache = RedisService()  # Initialize Redis


@router.get("/")
def health_check():
    """
    Health check endpoint to verify API status.
    """
    return {"message": "Product Search AI API is running!"}


@router.get("/search")
def search(
    query: str,
    store_apis: dict = Depends(get_store_apis),
):
    """
    AI-powered product search:
    1. Extracts product attributes from query (AI).
    2. Selects the best stores dynamically.
    3. Uses Redis cache to avoid redundant API calls.
    4. Fetches and ranks product data using FAISS & AI.
    """

    # Step 1: Check Redis cache
    cache_key = f"search:{query.lower()}"
    cached_results = redis_cache.get_cache(cache_key)
    if cached_results:
        return {"query": query, "cached": True, "results": cached_results}

    # Step 2: Fetch fresh product data if not cached
    fetcher = ProductFetcher()
    search_results = fetcher.fetch_products(query)

    # Step 3: Store results in Redis
    redis_cache.set_cache(cache_key, search_results)

    return {"query": query, "cached": False, "results": search_results}
