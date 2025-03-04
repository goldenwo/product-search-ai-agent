"""Service for fetching product search results via SERP APIs."""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from dotenv import load_dotenv

from src.models.product import Product
from src.utils import StoreAPIError, logger
from src.utils.config import SERP_API_KEY, SERP_API_URL

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
            StoreAPIError: If the API call fails
        """
        logger.info("🔍 Searching for products with query: %s", query)

        if not self.api_key:
            raise StoreAPIError("Missing SERP API key", "serp", 401)

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
                        raise StoreAPIError(f"SERP API returned status {response.status}", "serp", response.status)

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
            raise StoreAPIError(f"SERP API request failed: {str(e)}", "serp", 500) from e

        except (KeyError, ValueError, TypeError) as e:
            logger.error("❌ Error parsing SERP API response: %s", str(e))
            raise StoreAPIError(f"Error parsing SERP API response: {str(e)}", "serp", 500) from e

        except Exception as e:
            logger.error("❌ Unexpected error in SERP API service: %s", str(e))
            raise StoreAPIError(f"Unexpected error: {str(e)}", "serp", 500) from e

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
                    # Remove currency symbols and commas
                    price_str = price_str.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
                    price = Decimal(price_str)
                except (InvalidOperation, ValueError, TypeError):
                    price = Decimal("0.00")

                # Extract URL
                url = item.get("link", "")
                if not url:
                    logger.warning("⚠️ Skipping product with no URL")
                    continue

                # Extract product ID
                product_id = item.get("serpapi_product_api_id", "") or item.get("product_id", "") or item.get("source", "") + "_" + str(position)

                # Extract image URL
                image_url = item.get("imageUrl", "") or item.get("thumbnail", "")

                # Extract store
                source = item.get("source", "").lower() or self._extract_store_from_url(url)

                # Extract brand
                brand = item.get("brand", "") or self._extract_brand(title)

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
                if "reviews" in item:
                    try:
                        review_count = int(item["reviews"].replace(",", "").strip())
                    except (ValueError, TypeError, AttributeError):
                        pass

                # Extract offers
                offers = item.get("offers", item.get("merchant_count", ""))

                # Create Product object
                product = Product(
                    id=str(product_id),
                    title=title,
                    price=price,
                    store=source,
                    url=url,
                    image_url=image_url if image_url else None,
                    brand=brand if brand else None,
                    rating=rating,
                    review_count=review_count,
                    position=position,
                    shipping=shipping if shipping else None,
                    offers=str(offers) if offers else None,
                    source="serp_api",
                )

                normalized_products.append(product)

            except Exception as e:
                logger.error("❌ Error normalizing product: %s", str(e))
                continue

        return normalized_products

    def _extract_brand(self, title: str) -> str:
        """
        Extract brand name from product title using heuristics.

        Args:
            title: Product title

        Returns:
            str: Extracted brand name or empty string
        """
        if not title:
            return ""

        # Common brand indicators in title
        brand_indicators = [" by ", " from ", " - "]

        for indicator in brand_indicators:
            if indicator in title:
                parts = title.split(indicator, 1)
                if len(parts) > 1:
                    # If "by Brand", brand is after the indicator
                    if indicator == " by " or indicator == " from ":
                        potential_brand = parts[1].split(" ", 1)[0].strip()
                        if len(potential_brand) > 1:  # Avoid single letters
                            return potential_brand
                    # If "Brand - Product", brand is before the indicator
                    elif indicator == " - ":
                        return parts[0].strip()

        # If no indicators found, try to get the first word if it's capitalized
        first_word = title.split(" ", 1)[0]
        if first_word.istitle() and len(first_word) > 1:
            return first_word

        return ""

    def _extract_store_from_url(self, url: str) -> str:
        """
        Extract store name from URL.

        Args:
            url: Product URL

        Returns:
            str: Store name or "unknown"
        """
        try:
            domain = urlparse(url).netloc
            parts = domain.split(".")
            if len(parts) >= 2:
                return parts[-2].lower()
        except Exception:
            pass
        return "unknown"
