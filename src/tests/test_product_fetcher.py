"""Test the ProductFetcher class."""

from unittest.mock import Mock, patch

import numpy as np
import pytest
import requests

from src.ai_agent.product_fetcher import ProductFetcher


@pytest.fixture
def product_fetcher():
    """Create a ProductFetcher instance for testing."""
    fetcher = ProductFetcher()

    # Mock StoreSelector
    fetcher.store_selector = Mock()
    fetcher.store_selector.select_best_stores.return_value = ["Amazon", "BestBuy"]

    # Mock QueryParser
    fetcher.query_parser = Mock()
    fetcher.query_parser.extract_product_attributes.return_value = {"category": "electronics"}
    fetcher.query_parser.refine_query_for_store.return_value = {"keywords": "test query"}

    # Mock StoreConfig
    fetcher.store_config = Mock()
    fetcher.store_config.get_store_config.return_value = {
        "name": "Amazon",
        "api_url": "https://api.amazon.com",
        "api_key": "test-key",
        "allowed_params": ["keywords", "category"],
    }
    fetcher.store_config.get_allowed_params.return_value = ["keywords", "category"]

    # Mock OpenAIService
    fetcher.openai_service = Mock()
    fetcher.openai_service.generate_embedding.return_value = np.array([0.1] * 128)
    fetcher.openai_service.generate_response.return_value = '{"category": "electronics"}'

    return fetcher


@patch("src.ai_agent.product_fetcher.ProductFetcher.fetch_from_store")
def test_fetch_products_success(mock_fetch_from_store, product_fetcher):  # pylint: disable=redefined-outer-name
    """Test successful product fetching flow."""
    mock_fetch_from_store.return_value = [
        {"name": "ASUS ROG Gaming Laptop", "price": 999, "url": "https://amazon.com/product123", "store": "Amazon"},
        {"name": "Dell G5 Gaming Laptop", "price": 899, "url": "https://bestbuy.com/product456", "store": "BestBuy"},
    ]

    query = "best gaming laptop under $1000"
    products = product_fetcher.fetch_products(query)

    assert isinstance(products, list)
    assert len(products) > 0
    assert all(key in products[0] for key in ["name", "price", "url", "store", "relevance_score"])
    assert 0 <= products[0]["relevance_score"] <= 1
    mock_fetch_from_store.assert_called()


@patch("src.services.openai_service.OpenAIService.generate_response")
@patch("src.ai_agent.product_fetcher.ProductFetcher.fetch_from_store")
def test_fetch_products_no_results(mock_fetch_from_store, mock_openai, product_fetcher):  # pylint: disable=redefined-outer-name
    """Test handling of no results."""
    mock_openai.return_value = '{"category": "electronics", "product": "nonexistent"}'
    mock_fetch_from_store.return_value = []

    products = product_fetcher.fetch_products("nonexistent product")
    assert isinstance(products, list)
    assert len(products) == 0


def test_fetch_products_api_error(product_fetcher):  # pylint: disable=redefined-outer-name
    """Test handling of API errors."""
    product_fetcher.query_parser.extract_product_attributes.return_value = {"error": "API Error"}
    product_fetcher.query_parser.refine_query_for_store.return_value = {"error": "API Error"}

    products = product_fetcher.fetch_products("test query")
    assert isinstance(products, list)
    assert len(products) == 0


def test_generate_embeddings(product_fetcher):  # pylint: disable=redefined-outer-name
    """Test embedding generation."""
    test_products = [
        {"name": "Test Product 1", "description": "Description 1"},
        {"name": "Test Product 2", "description": "Description 2"},
    ]

    # Mock the OpenAI service's generate_embedding method
    product_fetcher.openai_service.generate_embedding = Mock(return_value=np.array([0.1] * 128))

    embeddings = product_fetcher.generate_embeddings(test_products)
    assert embeddings.shape == (2, 128)  # Assuming 128-dimensional embeddings


@patch("requests.get")
def test_fetch_from_store_success(mock_requests, product_fetcher):  # pylint: disable=redefined-outer-name
    """Test successful store API fetch."""
    mock_requests.return_value.status_code = 200
    mock_requests.return_value.json.return_value = [{"name": "Product 1", "price": 100}, {"name": "Product 2", "price": 200}]

    products = product_fetcher.fetch_from_store("amazon", {"keywords": "test"})
    assert len(products) == 2
    assert all("store" in product for product in products)


@patch("requests.get")
def test_fetch_from_store_error(mock_requests, product_fetcher):  # pylint: disable=redefined-outer-name
    """Test handling of store API errors."""
    mock_requests.side_effect = requests.RequestException("API Error")

    products = product_fetcher.fetch_from_store("amazon", {"keywords": "test"})
    assert isinstance(products, list)
    assert len(products) == 0
