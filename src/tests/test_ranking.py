"""Test the ProductRanker class."""

import numpy as np
import pytest

from src.ai_agent.ranking import ProductRanker


@pytest.fixture
def ranker():
    """Returns an instance of ProductRanker."""
    return ProductRanker()


def test_rank_products(product_ranker):
    """Test if products are ranked correctly based on vector similarity."""
    # Test data
    product_vectors = np.array([[0.1, 0.8, 0.3], [0.2, 0.7, 0.5], [0.3, 0.6, 0.4]], dtype=np.float32)

    product_metadata = [
        {"name": "Product A", "price": 500, "store": "Amazon"},
        {"name": "Product B", "price": 450, "store": "BestBuy"},
        {"name": "Product C", "price": 400, "store": "Amazon"},
    ]

    query_vector = np.array([0.1, 0.8, 0.3], dtype=np.float32)

    ranked_products = product_ranker.rank_products(query_vector=query_vector, product_vectors=product_vectors, product_metadata=product_metadata)

    assert isinstance(ranked_products, list)
    assert len(ranked_products) > 0
    assert all(key in ranked_products[0] for key in ["name", "score", "price", "store"])
    assert 0 <= ranked_products[0]["score"] <= 1
