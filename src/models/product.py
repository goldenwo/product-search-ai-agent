"""Product data models for consistent representation across stores."""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


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
    """

    id: str = Field(..., description="Unique product identifier")
    title: str = Field(..., description="Product name/title")
    price: Decimal = Field(..., description="Price in decimal format")
    store: str = Field(..., description="Store name (e.g., 'amazon', 'bestbuy')")
    url: HttpUrl = Field(..., description="Product page URL")

    description: Optional[str] = Field(default=None, description="Product description")
    category: Optional[str] = Field(default=None, description="Product category")
    brand: Optional[str] = Field(default=None, description="Brand name")
    image_url: Optional[HttpUrl] = Field(default=None, description="Product image URL")
    relevance_score: Optional[float] = Field(default=None, description="Search relevance score")

    class Config:
        """Pydantic model configuration."""

        json_encoders = {
            Decimal: str  # Convert Decimal to string for JSON serialization
        }
