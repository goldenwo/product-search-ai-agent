"""Normalizers for transforming raw API data into structured product models."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from src.models.product import Product
from src.utils import logger


class ProductNormalizer:
    """
    Normalizes raw product data from various sources into consistent Product objects.

    Provides dedicated normalizers for different data sources.
    """

    @staticmethod
    def normalize_serp_product(item: Dict[str, Any], position: int) -> Optional[Product]:
        """
        Normalize a single product result from SERP API into a Product object.

        Args:
            item: Raw product data from SERP API
            position: Position in search results

        Returns:
            Product: Normalized product or None if invalid
        """
        try:
            # Extract product data
            title = item.get("title", "").strip()

            if not title:
                logger.warning("⚠️ Skipping product with no title")
                return None

            # Parse price
            price = ProductNormalizer._parse_price(item.get("price", "0"))

            # Extract URL
            url = item.get("link", "")
            if not url:
                logger.warning("⚠️ Skipping product with no URL")
                return None

            # Extract store directly from API response's "source" field
            # This is the retailer name (e.g., "Sam's Club", "Uniqlo", "H&M")
            store = item.get("source", "").lower()

            # Extract product ID
            product_id = (
                item.get("productId", "") or item.get("product_id", "") or item.get("serpapi_product_api_id", "") or f"{store}_{str(position)}"
            )

            # Extract image URL
            image_url = item.get("imageUrl", "") or item.get("thumbnail", "")

            # Extract shipping info
            shipping = item.get("delivery", item.get("shipping", ""))

            # Extract rating and reviews
            rating = ProductNormalizer._parse_rating(item)
            review_count = ProductNormalizer._parse_review_count(item)

            # Extract offers as raw string, no parsing needed
            offers_str = item.get("offers", item.get("merchant_count", ""))

            # Extract product condition
            condition = ProductNormalizer._detect_condition(item.get("price", ""))

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

            return product

        except Exception as e:
            logger.error("❌ Error normalizing product: %s", str(e))
            return None

    @staticmethod
    def _parse_price(price_str: str) -> Decimal:
        """
        Parse price string into Decimal value.

        Args:
            price_str: Raw price string from API

        Returns:
            Decimal: Parsed price or 0.00 if invalid
        """
        try:
            # Remove currency symbols
            price_str = price_str.replace("$", "").replace("€", "").replace("£", "").strip()

            # Extract just the numeric part (first number with decimal if present)
            numeric_match = re.search(r"(\d+(?:\.\d+)?)", price_str)
            if numeric_match:
                price_str = numeric_match.group(1)
            else:
                price_str = "0.00"

            return Decimal(price_str)
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0.00")

    @staticmethod
    def _parse_rating(item: Dict[str, Any]) -> Optional[float]:
        """
        Parse product rating from raw data.

        Args:
            item: Raw product data

        Returns:
            float: Rating value or None if not available
        """
        if "rating" in item:
            try:
                return float(item["rating"])
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def _parse_review_count(item: Dict[str, Any]) -> Optional[int]:
        """
        Parse review count from raw data.

        Args:
            item: Raw product data

        Returns:
            int: Review count or None if not available
        """
        if "ratingCount" in item and item["ratingCount"]:
            try:
                return int(item["ratingCount"])
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def _detect_condition(price_str: str) -> Optional[str]:
        """
        Detect product condition from price string.

        Args:
            price_str: Raw price string

        Returns:
            str: Detected condition or None if not detected
        """
        price_lower = price_str.lower()

        if " refurbished" in price_lower:
            return "refurbished"
        elif " used" in price_lower:
            return "used"
        elif " renewed" in price_lower:
            return "renewed"
        elif " new" in price_lower:
            return "new"

        return None
