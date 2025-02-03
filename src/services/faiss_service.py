import faiss
import numpy as np


class FAISSService:
    """
    Handles FAISS vector search.
    """

    def __init__(self, vector_dimension: int = 3):
        """
        Initializes FAISS index with a given vector dimension.
        """
        self.vector_dimension = vector_dimension
        self.index = faiss.IndexFlatL2(self.vector_dimension)

    def add_vectors(self, vectors: np.ndarray):
        """
        Adds product vectors to FAISS index.
        """
        if vectors.shape[1] != self.vector_dimension:
            raise ValueError(f"❌ Vector dimension mismatch! Expected {self.vector_dimension}, got {vectors.shape[1]}")

        self.index.add(vectors)

    def search_similar_products(self, vector: np.ndarray, top_k: int = 5):
        """
        Searches FAISS for the most similar products.
        """
        if len(vector) != self.vector_dimension:
            raise ValueError(f"❌ Search vector dimension mismatch! Expected {self.vector_dimension}, got {len(vector)}")

        if self.index.ntotal == 0:
            raise ValueError("❌ FAISS index is empty! Add vectors before searching.")

        D, indices = self.index.search(np.array([vector], dtype=np.float32), top_k)

        valid_indices = [i for i in indices[0] if i >= 0]

        return valid_indices
