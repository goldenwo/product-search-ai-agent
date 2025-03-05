"""Service for fetching product search results via SERP APIs."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv

from src.models.product import Product
from src.utils import logger
from src.utils.config import SERP_API_KEY, SERP_API_URL
from src.utils.exceptions import SerpAPIException

# Load environment variables
load_dotenv()


class SerpService:
    """
    Service for fetching product search results from SERP API providers.

    Supports serper.dev API for product search.

    Attributes:
        api_key: API key for the SERP provider
        api_url: Base URL for the SERP API
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        """
        Initialize SERP service with API credentials.

        Args:
            api_key: Optional API key override
            api_url: Optional API URL override
        """
        self.api_key = api_key or SERP_API_KEY
        self.api_url = api_url or SERP_API_URL

        if not self.api_key:
            logger.warning("⚠️ No SERP API key provided. API calls will fail.")

    async def search_products(self, query: str, num_results: int = 10) -> List[Product]:
        """
        Search for products using the SERP API.

        Args:
            query: Search query
            num_results: Maximum number of results to return

        Returns:
            List[Product]: List of normalized product objects

        Raises:
            SerpAPIException: If the API call fails
        """
        logger.info("🔍 Searching for products with query: %s", query)

        if not self.api_key:
            raise SerpAPIException("Missing SERP API key", "serp", 401)

        try:
            # Headers for the serper.dev API
            headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}

            # Payload for the serper.dev API
            payload = {"q": query, "num": num_results}

            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload, timeout=20) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error("❌ SERP API error: %s", error_text)
                        raise SerpAPIException(f"SERP API returned status {response.status}", "serp", response.status)

                    data = await response.json()

                    # Check remaining credits from response
                    if "credits" in data:
                        logger.info("💰 Remaining SERP API credits: %s", data.get("credits"))

                    # Extract shopping results from the response (serper.dev uses "shopping" key)
                    shopping_results = data.get("shopping", [])
                    if not shopping_results:
                        logger.warning("⚠️ No shopping results found in SERP response")
                        return []

                    if not isinstance(shopping_results, list):
                        logger.warning("⚠️ Invalid shopping results format")
                        return []

                    # Normalize the results into Product objects
                    normalized_products = self._normalize_results(shopping_results)

                    logger.info("✅ Found %d products for query '%s'", len(normalized_products), query)
                    return normalized_products

        except aiohttp.ClientError as e:
            logger.error("❌ SERP API request failed: %s", str(e))
            raise SerpAPIException(f"SERP API request failed: {str(e)}", "serp", 500) from e

        except (KeyError, ValueError, TypeError) as e:
            logger.error("❌ Error parsing SERP API response: %s", str(e))
            raise SerpAPIException(f"Error parsing SERP API response: {str(e)}", "serp", 500) from e

        except Exception as e:
            logger.error("❌ Unexpected error in SERP API service: %s", str(e))
            raise SerpAPIException(f"Unexpected error: {str(e)}", "serp", 500) from e

    def _normalize_results(self, results: List[Dict[str, Any]]) -> List[Product]:
        """
        Normalize raw API results into Product objects.

        Args:
            results: Raw product data from API

        Returns:
            List[Product]: List of normalized Product objects
        """
        normalized_products = []
        position = 0

        for item in results:
            position += 1
            try:
                # Extract product data
                title = item.get("title", "").strip()

                if not title:
                    logger.warning("⚠️ Skipping product with no title")
                    continue

                # Parse price
                price_str = item.get("price", "0")
                try:
                    # Extract only numeric characters and decimal points
                    # First remove currency symbols
                    price_str = price_str.replace("$", "").replace("€", "").replace("£", "").strip()
                    # Then extract just the numeric part (first number with decimal if present)
                    numeric_match = re.search(r"(\d+(?:\.\d+)?)", price_str)
                    if numeric_match:
                        price_str = numeric_match.group(1)
                    else:
                        price_str = "0.00"

                    price = Decimal(price_str)
                except (InvalidOperation, ValueError, TypeError):
                    price = Decimal("0.00")

                # Extract URL
                url = item.get("link", "")
                if not url:
                    logger.warning("⚠️ Skipping product with no URL")
                    continue

                # Extract store directly from API response's "source" field
                # This is the retailer name (e.g., "Sam's Club", "Uniqlo", "H&M")
                store = item.get("source", "").lower()

                # No explicit brand field in the response, so don't try to extract it
                # The brand might be part of the title, but we won't attempt to parse it here

                # Extract product ID
                product_id = (
                    item.get("productId", "") or item.get("product_id", "") or item.get("serpapi_product_api_id", "") or f"{store}_{str(position)}"
                )

                # Extract image URL
                image_url = item.get("imageUrl", "") or item.get("thumbnail", "")

                # Extract shipping info
                shipping = item.get("delivery", item.get("shipping", ""))

                # Extract rating
                rating = None
                if "rating" in item:
                    try:
                        rating = float(item["rating"])
                    except (ValueError, TypeError):
                        pass

                # Extract review count
                review_count = None
                if "ratingCount" in item and item["ratingCount"]:
                    try:
                        review_count = int(item["ratingCount"])
                    except (ValueError, TypeError):
                        pass

                # Extract offers as raw string, no parsing needed
                offers_str = item.get("offers", item.get("merchant_count", ""))

                # Extract product condition
                condition = None
                if "price" in item:
                    price_str = item.get("price", "")
                    if " refurbished" in price_str.lower():
                        condition = "refurbished"
                    elif " used" in price_str.lower():
                        condition = "used"
                    elif " renewed" in price_str.lower():
                        condition = "renewed"
                    elif " new" in price_str.lower():
                        condition = "new"

                # Add specifications if available
                specifications = {}
                if condition:
                    specifications["condition"] = condition

                # Create Product object with additional fields
                product = Product(
                    id=str(product_id),
                    title=title,
                    price=price,
                    store=store,  # Set store using the "source" field from API
                    url=url,
                    image_url=image_url if image_url else None,
                    brand=None,  # No direct brand information from the API
                    category=None,
                    rating=rating,
                    review_count=review_count,
                    position=position,
                    shipping=shipping if shipping else None,
                    offers=offers_str if offers_str else None,
                    source="serp_api",  # This indicates where the data came from
                    specifications=specifications,
                )

                normalized_products.append(product)

            except Exception as e:
                logger.error("❌ Error normalizing product: %s", str(e))
                continue

        return normalized_products
