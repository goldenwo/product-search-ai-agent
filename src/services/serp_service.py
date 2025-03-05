"""Service for fetching product search results via SERP APIs."""

from typing import List, Optional

from src.models.product import Product
from src.services.clients.serp_api_client import SerpAPIClient
from src.services.normalizers.product_normalizer import ProductNormalizer
from src.utils import logger


class SerpService:
    """
    Service for fetching and normalizing product search results from SERP API providers.

    Implements a clean separation between API interaction and data normalization.

    Attributes:
        api_client: Client for interacting with the SERP API
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        """
        Initialize SERP service with API client.

        Args:
            api_key: Optional API key override
            api_url: Optional API URL override
        """
        self.api_client = SerpAPIClient(api_key=api_key, api_url=api_url)

    async def search_products(self, query: str, num_results: int = 10) -> List[Product]:
        """
        Search for products using the SERP API and normalize results.

        Args:
            query: Search query
            num_results: Maximum number of results to return

        Returns:
            List[Product]: List of normalized product objects

        Raises:
            SerpAPIException: If the API call fails
        """
        logger.info("🔍 Searching for products with query: %s", query)

        # Fetch raw product data from the API
        raw_results = await self.api_client.search_products(query, num_results)

        # Normalize the results into Product objects
        normalized_products = self._normalize_results(raw_results)

        logger.info("✅ Found %d products for query '%s'", len(normalized_products), query)
        return normalized_products

    def _normalize_results(self, results: List[dict]) -> List[Product]:
        """
        Normalize raw API results into Product objects using the ProductNormalizer.

        Args:
            results: Raw product data from API

        Returns:
            List[Product]: List of normalized Product objects
        """
        normalized_products = []

        for position, item in enumerate(results, start=1):
            product = ProductNormalizer.normalize_serp_product(item, position)
            if product:
                normalized_products.append(product)

        return normalized_products
