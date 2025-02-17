"""Test the ProductRanker class."""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.ai_agent.product_ranker import ProductRanker


@pytest.fixture
@patch("src.ai_agent.product_ranker.FAISSService")
def product_ranker(mock_faiss):
    """Create a ProductRanker with mocked FAISS service."""
    # Configure mock FAISS service
    mock_faiss_instance = Mock()
    mock_faiss_instance.vector_dimension = 128
    mock_faiss_instance.add_vectors = Mock()
    mock_faiss_instance.search_similar_products = Mock(return_value=[0])
    mock_faiss.return_value = mock_faiss_instance

    return ProductRanker()


def test_rank_products_success(product_ranker):  # pylint: disable=redefined-outer-name
    """Test successful product ranking."""
    query_vector = np.array([0.1] * 128)
    product_vectors = np.array([[0.1] * 128, [0.2] * 128])
    product_metadata = [{"name": "Product 1", "price": "99.99", "store": "Store A"}, {"name": "Product 2", "price": "149.99", "store": "Store B"}]

    ranked_products = product_ranker.rank_products(query_vector, product_vectors, product_metadata)

    assert isinstance(ranked_products, list)
    assert len(ranked_products) > 0
    assert all(key in ranked_products[0] for key in ["name", "score", "price", "store"])
    assert 0 <= ranked_products[0]["score"] <= 1


def test_rank_products_empty_inputs(product_ranker):  # pylint: disable=redefined-outer-name
    """Test handling of empty inputs."""
    query_vector = np.array([0.1] * 128)
    empty_vectors = np.array([]).reshape(0, 128)
    empty_metadata = []

    ranked_products = product_ranker.rank_products(query_vector, empty_vectors, empty_metadata)
    assert isinstance(ranked_products, list)
    assert len(ranked_products) == 0


@patch("src.ai_agent.product_ranker.FAISSService")
def test_rank_products_invalid_dimensions(mock_faiss, product_ranker):  # pylint: disable=redefined-outer-name
    """Test handling of invalid vector dimensions."""
    query_vector = np.array([0.1] * 128)  # Correct dimension
    product_vectors = np.array([[0.1] * 64])  # Wrong dimension
    product_metadata = [{"name": "Product 1", "price": "99.99", "store": "Store A"}]

    with pytest.raises(ValueError, match="FAISS expects.*dimensional vectors"):
        product_ranker.rank_products(query_vector, product_vectors, product_metadata)


def test_rank_products_invalid_query_vector(product_ranker):  # pylint: disable=redefined-outer-name
    """Test handling of invalid query vector."""
    query_vector = np.array([[0.1] * 128])  # 2D array instead of 1D
    product_vectors = np.array([[0.1] * 128])
    product_metadata = [{"name": "Product 1", "price": "99.99", "store": "Store A"}]

    with pytest.raises(ValueError, match="Query vector must be a 1D NumPy array"):
        product_ranker.rank_products(query_vector, product_vectors, product_metadata)


def test_rank_products_invalid_product_vectors(product_ranker):  # pylint: disable=redefined-outer-name
    """Test handling of invalid product vectors."""
    query_vector = np.array([0.1] * 128)
    product_vectors = np.array([0.1] * 128)  # 1D array instead of 2D
    product_metadata = [{"name": "Product 1", "price": "99.99", "store": "Store A"}]

    with pytest.raises(ValueError, match="Product vectors must be a 2D NumPy array"):
        product_ranker.rank_products(query_vector, product_vectors, product_metadata)


def test_rank_products_metadata_mismatch(product_ranker):  # pylint: disable=redefined-outer-name
    """Test handling of metadata length mismatch."""
    query_vector = np.array([0.1] * 128)
    product_vectors = np.array([[0.1] * 128, [0.2] * 128])
    product_metadata = [{"name": "Product 1", "price": "99.99", "store": "Store A"}]  # One item short

    with pytest.raises(ValueError, match="Product metadata length must match"):
        product_ranker.rank_products(query_vector, product_vectors, product_metadata)


def test_rank_products_missing_metadata_fields(product_ranker):  # pylint: disable=redefined-outer-name
    """Test handling of missing metadata fields."""
    query_vector = np.array([0.1] * 128)
    product_vectors = np.array([[0.1] * 128])
    product_metadata = [{"name": "Product 1"}]  # Missing price and store

    ranked_products = product_ranker.rank_products(query_vector, product_vectors, product_metadata)
    assert isinstance(ranked_products, list)
    assert len(ranked_products) > 0
    assert ranked_products[0]["price"] == "N/A"
    assert ranked_products[0]["store"] == "Unknown"


def test_rank_products_score_ordering(product_ranker):  # pylint: disable=redefined-outer-name
    """Test that products are properly ordered by similarity score."""
    query_vector = np.array([0.1] * 128)
    product_vectors = np.array([[0.1] * 128, [0.2] * 128, [0.3] * 128])
    product_metadata = [
        {"name": "Product 1", "price": "99.99", "store": "Store A"},
        {"name": "Product 2", "price": "149.99", "store": "Store B"},
        {"name": "Product 3", "price": "199.99", "store": "Store C"},
    ]

    ranked_products = product_ranker.rank_products(query_vector, product_vectors, product_metadata)

    # Check that scores are in descending order
    scores = [p["score"] for p in ranked_products]
    assert scores == sorted(scores, reverse=True)


def test_rank_products_top_k_limit(product_ranker):  # pylint: disable=redefined-outer-name
    """Test that top_k parameter correctly limits results."""
    query_vector = np.array([0.1] * 128)
    product_vectors = np.array([[0.1] * 128] * 10)  # 10 products
    product_metadata = [{"name": f"Product {i}", "price": "99.99", "store": "Store A"} for i in range(10)]

    top_k = 5
    ranked_products = product_ranker.rank_products(query_vector, product_vectors, product_metadata, top_k=top_k)
    assert len(ranked_products) == top_k
