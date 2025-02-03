import pytest
from unittest.mock import patch
from src.ai_agent.product_fetcher import ProductFetcher
from src.services.faiss_service import FAISSService

@pytest.fixture
def product_fetcher():
    faiss_service = FAISSService(vector_dimension=128)
    return ProductFetcher(faiss_service)

@patch("src.services.openai_service.OpenAIService.generate_response")
@patch("src.ai_agent.product_fetcher.ProductFetcher.fetch_from_store")
def test_fetch_products(mock_fetch_from_store, mock_openai, product_fetcher):
    """
    Test if AI fetches product data from stores.
    """
    mock_openai.return_value = '{"category": "electronics", "product": "gaming laptop", "budget": "1000"}'
    mock_fetch_from_store.return_value = [
        {"name": "ASUS ROG Gaming Laptop", "price": 999, "url": "https://amazon.com/product123", "store": "Amazon"},
        {"name": "Dell G5 Gaming Laptop", "price": 899, "url": "https://bestbuy.com/product456", "store": "BestBuy"}
    ]

    query = "best gaming laptop under $1000"
    products = product_fetcher.fetch_products(query)

    assert isinstance(products, list)
    assert len(products) > 0
    assert "name" in products[0]
    assert "price" in products[0]
    assert "url" in products[0]
    assert "store" in products[0]

    assert mock_openai.call_count == 2
    mock_fetch_from_store.assert_called()