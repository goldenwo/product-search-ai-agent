"""FAISS vector search service for efficient similarity-based product recommendations."""

import faiss
import numpy as np

from src.utils import FAISS_VECTOR_DIMENSION, logger


class FAISSService:
    """
    Handles FAISS vector search for real-time AI-based product recommendations.
    Optimized for fast, temporary in-memory search (NO persistent storage).
    """

    def __init__(self):
        """
        Initializes FAISS with an in-memory index (IndexFlatL2).
        """
        if FAISS_VECTOR_DIMENSION <= 0:
            raise ValueError("❌ Vector dimension must be greater than 0")

        self.vector_dimension = FAISS_VECTOR_DIMENSION
        self.index = faiss.IndexFlatL2(self.vector_dimension)  # Always use exact search

    def add_vectors(self, vectors: np.ndarray):
        """
        Adds vectors to FAISS.
        """
        if not isinstance(vectors, np.ndarray):
            raise TypeError("❌ Input vectors must be a NumPy array")

        if vectors.ndim == 1:  # Ensure 2D shape
            vectors = np.expand_dims(vectors, axis=0)

        vectors = vectors.astype(np.float32)  # Convert to float32

        if vectors.shape[1] != self.vector_dimension:
            raise ValueError(f"❌ Vector dimension mismatch! Expected {self.vector_dimension}, got {vectors.shape[1]}")

        # pylint: disable = no-value-for-parameter
        self.index.add(vectors)  # type: ignore[call-arg] # Directly add to FAISS

    def search_similar_products(self, vector: np.ndarray, top_k: int = 5):
        """
        Searches for top-K most similar products using FAISS.
        """
        if self.index.ntotal == 0:
            logger.warning("⚠️ FAISS index is empty! Add vectors before searching.")
            return None

        if vector.ndim == 1:
            vector = np.expand_dims(vector, axis=0)  # Ensure 2D input

        vector = vector.astype(np.float32)  # Convert to float32

        # pylint: disable = no-value-for-parameter
        _, indices = self.index.search(vector, top_k)  # type: ignore[call-arg] # Perform similarity search

        return [i for i in indices[0] if i >= 0]  # Filter valid results
