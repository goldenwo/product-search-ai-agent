"""Product data models for consistent representation across stores."""

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Product(BaseModel):
    """
    Normalized product model for consistent handling across stores.

    Attributes:
        id: Unique product identifier
        title: Product name/title
        price: Price in decimal format
        store: Store name (e.g., "amazon", "bestbuy")
        url: Product page URL
        description: Optional product description
        category: Optional product category
        brand: Optional brand name
        image_url: Optional product image URL
        relevance_score: Optional search relevance score
        rating: Optional product rating (0-5)
        review_count: Optional number of reviews
        shipping: Optional shipping information
        offers: Optional number of offers/sellers
        position: Optional position in search results
        specifications: Optional detailed product specifications
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"id": "123", "title": "Gaming Laptop", "price": "999.99", "store": "amazon", "url": "https://amazon.com/p/123"}
        },
        from_attributes=True,
        arbitrary_types_allowed=True,
    )

    id: str = Field(..., description="Unique product identifier")
    title: str = Field(..., description="Product name/title")
    price: Decimal = Field(..., description="Price in decimal format")
    store: str = Field(..., description="Store name (e.g., 'amazon', 'bestbuy')")
    url: HttpUrl = Field(..., description="Product page URL")

    description: Optional[str] = Field(default=None, description="Product description")
    category: Optional[str] = Field(default=None, description="Product category")
    brand: Optional[str] = Field(default=None, description="Brand name")
    image_url: Optional[HttpUrl] = Field(default=None, description="Product image URL")

    # Search-related attributes
    relevance_score: Optional[float] = Field(default=None, description="Search relevance score")
    relevance_explanation: Optional[str] = Field(default=None, description="Explanation of relevance score")

    # Rating and reviews
    rating: Optional[float] = Field(default=None, description="Product rating (0-5)")
    review_count: Optional[int] = Field(default=None, description="Number of reviews")

    # Shipping and purchase info
    shipping: Optional[str] = Field(default=None, description="Shipping information")
    offers: Optional[str] = Field(default=None, description="Number of offers/sellers")

    # Search result metadata
    position: Optional[int] = Field(default=None, description="Position in search results")
    source: Optional[str] = Field(default=None, description="Source of product data")

    # Detailed specifications
    specifications: Optional[dict[str, Any]] = Field(default=None, description="Detailed product specifications")
