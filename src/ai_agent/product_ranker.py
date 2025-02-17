import numpy as np

from src.services import FAISSService
from src.utils import logger


class ProductRanker:
    """
    Ranks products based on similarity using FAISS.
    Optimized for efficiency and edge case handling.
    """

    def __init__(self):
        """
        Initializes FAISS service with a shared instance.
        """
        self.faiss_service = FAISSService()  # Uses FAISS_VECTOR_DIMENSION from .env

    def rank_products(self, query_vector: np.ndarray, product_vectors: np.ndarray, product_metadata: list[dict], top_k: int = 5):
        """
        Ranks products based on similarity using FAISS.

        :param query_vector: AI-generated query vector (1D NumPy array)
        :param product_vectors: List of product vectors (2D NumPy array)
        :param product_metadata: Corresponding metadata for each product
        :param top_k: Number of top-ranked products to return
        :return: List of ranked products
        """
        # 🚀 **Step 1: Validate Inputs**
        if not isinstance(query_vector, np.ndarray) or query_vector.ndim != 1:
            raise ValueError("❌ Query vector must be a 1D NumPy array")

        if not isinstance(product_vectors, np.ndarray) or product_vectors.ndim != 2:
            raise ValueError("❌ Product vectors must be a 2D NumPy array")

        if len(product_vectors) != len(product_metadata):
            raise ValueError("❌ Product metadata length must match the number of vectors")

        if product_vectors.shape[1] != self.faiss_service.vector_dimension:
            raise ValueError(f"❌ FAISS expects {self.faiss_service.vector_dimension}-dimensional vectors, got {product_vectors.shape[1]}")

        # 🚀 **Step 2: Reset FAISS & Add Vectors Efficiently**
        self.faiss_service = FAISSService()  # Ensure fresh FAISS instance
        self.faiss_service.add_vectors(product_vectors)

        # 🚀 **Step 3: Search FAISS for Top Matches**
        similar_indices = self.faiss_service.search_similar_products(query_vector, top_k)

        if not similar_indices:
            logger.warning("⚠️ No similar products found!")
            return []

        # 🚀 **Step 4: Retrieve and Sort Ranked Products**
        ranked_products = [
            {
                "name": product_metadata[i]["name"],
                "score": round(1.0 - (rank / len(product_vectors)), 4),  # Approximate similarity score
                "price": product_metadata[i].get("price", "N/A"),
                "store": product_metadata[i].get("store", "Unknown"),
            }
            for rank, i in enumerate(similar_indices)
        ]

        return ranked_products
