from fastapi import APIRouter

from src.ai_agent.product_fetcher import ProductFetcher
from src.services.redis_service import RedisService
from src.utils import logger

router = APIRouter()
redis_cache = RedisService()  # Initialize Redis


@router.get("/")
def health_check():
    """
    Health check endpoint to verify API status.
    """
    return {"message": "Product Search AI API is running!"}


@router.get("/search")
async def search(query: str):
    """
    AI-powered product search:
    1. Extracts product attributes from query (AI).
    2. Selects the best stores dynamically.
    3. Uses Redis cache to avoid redundant API calls.
    4. Fetches and ranks product data using FAISS & AI.
    """
    query = query.strip()
    if not query:
        return {"error": "Empty search query"}

    try:
        # Step 1: Check Redis cache
        cache_key = f"search:{query.lower()}"
        cached_results = redis_cache.get_cache(cache_key)
        if cached_results:
            return {"query": query, "cached": True, "results": cached_results}

        # Step 2: Fetch fresh product data
        fetcher = ProductFetcher()
        search_results = await fetcher.fetch_products(query)

        if not search_results:
            return {"query": query, "results": [], "message": "No products found"}

        # Step 3: Cache results
        redis_cache.set_cache(cache_key, search_results)
        return {"query": query, "cached": False, "results": search_results}

    except Exception as e:
        logger.error("❌ Search error: %s", str(e))
        return {"error": "Search failed. Please try again later."}
