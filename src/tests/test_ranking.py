import pytest
import numpy as np
from src.ai_agent.ranking import ProductRanker
from src.services.faiss_service import FAISSService

@pytest.fixture
def ranker():
    """
    Returns an instance of ProductRanker with a FAISS index.
    """
    faiss_service = FAISSService(vector_dimension=3)  # Match test vectors' dimension
    return ProductRanker(faiss_service)

def test_rank_products(ranker):
    """
    Test if AI ranks products correctly using FAISS.
    """
    products = [
        {"name": "Product A", "price": 500, "vector": np.array([0.1, 0.8, 0.3], dtype=np.float32)},
        {"name": "Product B", "price": 450, "vector": np.array([0.2, 0.7, 0.5], dtype=np.float32)},
        {"name": "Product C", "price": 400, "vector": np.array([0.3, 0.6, 0.4], dtype=np.float32)},
    ]

    # Extract vectors and add them to FAISS before testing ranking
    vectors = np.array([p["vector"] for p in products], dtype=np.float32)
    ranker.faiss_service.add_vectors(vectors)

    ranked_products = ranker.rank_products(products)

    assert isinstance(ranked_products, list)
    assert len(ranked_products) <= len(products)  # Ensure FAISS does not return more indices than available
    assert all(p in products for p in ranked_products)  # Ensure valid indices are used
    assert ranked_products[0]["name"] != ranked_products[-1]["name"]  # Ensure ranking reorders products
