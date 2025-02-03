from typing import List, Dict
import numpy as np
from src.services.faiss_service import FAISSService

class ProductRanker:
    """
    AI-powered product ranking using FAISS similarity and AI-based scoring.
    """

    def __init__(self, faiss_service: FAISSService):
        self.faiss_service = faiss_service  # FAISS vector search service

    def rank_products(self, products: List[Dict]) -> List[Dict]:
        """
        Ranks products based on AI-enhanced scoring and FAISS vector similarity.

        Args:
            products (List[Dict]): List of fetched products.

        Returns:
            List[Dict]: Ranked product list.
        """
        if not products:
            return []

        # Step 1: Extract product vectors (assume vector embeddings exist)
        product_vectors = np.array([p["vector"] for p in products if "vector" in p], dtype=np.float32)

        if len(product_vectors) == 0:
            return sorted(products, key=lambda p: p.get("price", float("inf")))  # Default: Sort by price if no vectors

        # Step 2: Use FAISS to find top matches
        ranked_indices = self.faiss_service.search_similar_products(product_vectors[0], top_k=len(products))
        
        # Step 3: Reorder products based on FAISS ranking
        ranked_products = [products[i] for i in ranked_indices]

        return ranked_products
