"""Test the ProductFetcher class."""

from unittest.mock import Mock, patch

import pytest

from src.ai_agent.product_fetcher import ProductFetcher


@pytest.fixture
def product_fetcher():
    """Create a ProductFetcher instance for testing."""
    return ProductFetcher()


@patch("src.services.openai_service.OpenAIService.generate_response")
@patch("src.ai_agent.product_fetcher.ProductFetcher.fetch_from_store")
def test_fetch_products_success(mock_fetch_from_store, mock_openai, fetcher):
    """Test successful product fetching flow."""
    # Mock AI responses
    mock_openai.side_effect = [
        '{"category": "electronics", "product": "gaming laptop", "budget": "1000"}',  # Query parsing
        '["Amazon", "BestBuy"]',  # Store selection
    ]

    mock_fetch_from_store.return_value = [
        {"name": "ASUS ROG Gaming Laptop", "price": 999, "url": "https://amazon.com/product123", "store": "Amazon"},
        {"name": "Dell G5 Gaming Laptop", "price": 899, "url": "https://bestbuy.com/product456", "store": "BestBuy"},
    ]

    query = "best gaming laptop under $1000"
    products = fetcher.fetch_products(query)

    assert isinstance(products, list)
    assert len(products) > 0
    assert all(key in products[0] for key in ["name", "price", "url", "store", "relevance_score"])
    assert 0 <= products[0]["relevance_score"] <= 1
    assert mock_openai.call_count >= 2
    mock_fetch_from_store.assert_called()


@patch("src.services.openai_service.OpenAIService.generate_response")
@patch("src.ai_agent.product_fetcher.ProductFetcher.fetch_from_store")
def test_fetch_products_no_results(mock_fetch_from_store, mock_openai, fetcher):
    """Test handling of no results."""
    mock_openai.return_value = '{"category": "electronics", "product": "nonexistent"}'
    mock_fetch_from_store.return_value = []

    products = fetcher.fetch_products("nonexistent product")
    assert isinstance(products, list)
    assert len(products) == 0


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_fetch_products_api_error(mock_openai, fetcher):
    """Test handling of API errors."""
    mock_openai.side_effect = Exception("API Error")

    products = fetcher.fetch_products("test query")
    assert isinstance(products, list)
    assert len(products) == 0


def test_generate_embeddings(fetcher):
    """Test embedding generation."""
    test_products = [
        {"name": "Test Product 1", "description": "Description 1"},
        {"name": "Test Product 2", "description": "Description 2"},
    ]

    # Mock the OpenAI service's generate_embedding method
    fetcher.openai_service.generate_embedding = Mock(return_value=[0.1] * 128)

    embeddings = fetcher.generate_embeddings(test_products)
    assert embeddings.shape == (2, 128)  # Assuming 128-dimensional embeddings
