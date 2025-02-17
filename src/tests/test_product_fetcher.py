"""Test the ProductFetcher class."""

from decimal import Decimal
from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.ai_agent.product_fetcher import ProductFetcher
from src.models.product import Product
from src.utils import OpenAIServiceError


@pytest.fixture
def mock_product() -> Product:
    """Create a mock product for testing."""
    return Product(
        id="123",
        title="Test Product",
        price=Decimal("99.99"),
        store="amazon",
        url="https://amazon.com/p/123",
        description="Test description",
        category="electronics",
        brand="TestBrand",
        image_url="https://images.amazon.com/123.jpg",
    )


@pytest.fixture
def product_fetcher() -> ProductFetcher:
    """Create a ProductFetcher instance with mocked dependencies."""
    fetcher = ProductFetcher()

    # Mock dependencies
    fetcher.store_selector = Mock()
    fetcher.store_selector.select_best_stores.return_value = ["amazon", "bestbuy"]

    fetcher.query_parser = Mock()
    fetcher.query_parser.extract_product_attributes.return_value = {"category": "electronics"}
    fetcher.query_parser.refine_query_for_store.return_value = {"keywords": "test query"}

    fetcher.redis_cache = Mock()
    fetcher.redis_cache.get_cache.return_value = None

    fetcher.openai_service = Mock()
    fetcher.openai_service.generate_embedding.return_value = np.array([[0.1] * 128])

    return fetcher


@pytest.mark.asyncio
async def test_fetch_products_cached(product_fetcher, mock_product):  # pylint: disable=redefined-outer-name
    """Test fetching products when results are cached."""
    cached_results = [vars(mock_product)]
    product_fetcher.redis_cache.get_cache.return_value = cached_results

    results = await product_fetcher.fetch_products("test query")
    assert results == cached_results
    product_fetcher.query_parser.extract_product_attributes.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_products_no_cache(product_fetcher, mock_product):  # pylint: disable=redefined-outer-name
    """Test fetching products with no cache."""

    # Mock store API response
    async def mock_fetch_store(*args, **kwargs):
        return [mock_product]

    product_fetcher.fetch_from_store = Mock(side_effect=mock_fetch_store)

    results = await product_fetcher.fetch_products("test query")

    assert len(results) > 0
    assert "relevance_score" in results[0]
    assert product_fetcher.redis_cache.set_cache.called


@pytest.mark.asyncio
async def test_fetch_products_empty_query(product_fetcher):  # pylint: disable=redefined-outer-name
    """Test handling of empty query."""
    results = await product_fetcher.fetch_products("")
    assert results == []
    product_fetcher.redis_cache.get_cache.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_products_no_results(product_fetcher):  # pylint: disable=redefined-outer-name
    """Test handling of no results from stores."""

    async def mock_fetch_store(*args, **kwargs):
        return []

    product_fetcher.fetch_from_store = Mock(side_effect=mock_fetch_store)
    results = await product_fetcher.fetch_products("test query")
    assert results == []


@pytest.mark.asyncio
async def test_generate_embeddings(product_fetcher, mock_product):  # pylint: disable=redefined-outer-name
    """Test embedding generation for products."""
    embeddings = product_fetcher.generate_embeddings([mock_product])
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape[1] == 128  # Embedding dimension


@pytest.mark.asyncio
async def test_fetch_from_store_cached(product_fetcher, mock_product):  # pylint: disable=redefined-outer-name
    """Test fetching from store with cached results."""
    cached_products = [vars(mock_product)]
    product_fetcher.redis_cache.get_cache.return_value = cached_products

    results = await product_fetcher.fetch_from_store("amazon", {"keywords": "test"})
    assert len(results) == 1
    assert isinstance(results[0], Product)


@pytest.mark.asyncio
async def test_fetch_from_store_api_error(product_fetcher):  # pylint: disable=redefined-outer-name
    """Test handling of store API errors."""
    product_fetcher.redis_cache.get_cache.return_value = None
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.side_effect = Exception("API Error")

        results = await product_fetcher.fetch_from_store("amazon", {"keywords": "test"})
        assert results == []


@pytest.mark.asyncio
async def test_fetch_products_embedding_error(product_fetcher, mock_product):  # pylint: disable=redefined-outer-name
    """Test handling of embedding generation errors."""

    async def mock_fetch_store(*args, **kwargs):
        return [mock_product]

    product_fetcher.fetch_from_store = Mock(side_effect=mock_fetch_store)
    product_fetcher.openai_service.generate_embedding.side_effect = OpenAIServiceError("API Error")

    results = await product_fetcher.fetch_products("test query")
    assert results == []  # Should return empty list on embedding error
