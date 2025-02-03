import pytest
from src.ai_agent.product_fetcher import ProductFetcher
from src.services.faiss_service import FAISSService

@pytest.fixture
def product_fetcher():
    faiss_service = FAISSService(vector_dimension=128)
    return ProductFetcher(faiss_service)

def test_fetch_products(product_fetcher):
    """
    Test if AI fetches product data from stores.
    """
    query = "best gaming laptop under $1000"
    products = product_fetcher.fetch_products(query)

    assert isinstance(products, list)
    assert len(products) > 0
    assert "name" in products[0]
    assert "price" in products[0]
    assert "url" in products[0]
    assert "store" in products[0]
