import pytest
from src.ai_agent.ranking import ProductRanker
from src.services.faiss_service import FAISSService

@pytest.fixture
def ranker():
    faiss_service = FAISSService(vector_dimension=128)
    return ProductRanker(faiss_service)

def test_rank_products(ranker):
    """
    Test if AI ranks products correctly using FAISS.
    """
    products = [
        {"name": "Product A", "price": 500, "vector": [0.1, 0.8, 0.3]},
        {"name": "Product B", "price": 450, "vector": [0.2, 0.7, 0.5]},
        {"name": "Product C", "price": 400, "vector": [0.3, 0.6, 0.4]},
    ]

    ranked_products = ranker.rank_products(products)

    assert isinstance(ranked_products, list)
    assert len(ranked_products) == 3
    assert ranked_products[0]["name"] != ranked_products[-1]["name"]  # Ranking must reorder products
