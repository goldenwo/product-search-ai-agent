from typing import List, Dict
import numpy as np
from src.services.faiss_service import FAISSService

class ProductRanker:
    """
    AI-powered product ranking using FAISS similarity and AI-based scoring.
    """

    def __init__(self, faiss_service: FAISSService):
        self.faiss_service = faiss_service

    def rank_products(self, products: List[Dict]) -> List[Dict]:
        """
        Ranks products based on FAISS vector similarity.

        Args:
            products (List[Dict]): List of fetched products.

        Returns:
            List[Dict]: Ranked product list.
        """
        if not products:
            return []

        # Step 1: Extract valid product vectors
        product_vectors = [p["vector"] for p in products if "vector" in p and isinstance(p["vector"], np.ndarray)]
        if not product_vectors:
            return sorted(products, key=lambda p: p.get("price", float("inf")))  # Default: Sort by price if no vectors
        
        product_vectors = np.array(product_vectors, dtype=np.float32)

        # Step 2: Ensure vectors are added before searching
        self.faiss_service.add_vectors(product_vectors)

        # Step 3: Use FAISS to find top matches
        top_k = min(len(products), 3)  # Ensure `top_k` does not exceed product count
        ranked_indices = self.faiss_service.search_similar_products(product_vectors[0], top_k=top_k)

        # Step 4: Filter out invalid indices (`-1`)
        valid_indices = [i for i in ranked_indices if 0 <= i < len(products)]

        # Step 5: Ensure valid indices before reordering
        ranked_products = [products[i] for i in valid_indices]

        return ranked_products
