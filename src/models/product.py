"""Shared product model for consistent data across all store integrations."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class Product:
    """
    Common product model that all store responses must map to.

    Required fields:
    - id: Unique identifier within the store
    - title: Product name/title
    - price: Current price in decimal format
    - store: Store identifier (e.g., "amazon", "bestbuy")
    - url: Direct product URL

    Optional fields:
    - description: Full product description
    - category: Product category
    - brand: Manufacturer/brand name
    - image_url: Primary product image URL
    """

    id: str
    title: str
    price: Decimal
    store: str
    url: str
    description: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    image_url: Optional[str] = None
