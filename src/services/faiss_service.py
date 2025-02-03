import faiss
import numpy as np

class FAISSService:
    """Handles FAISS vector search for similar products."""
    
    def __init__(self, vector_dimension: int):
        self.index = faiss.IndexFlatL2(vector_dimension)
    
    def store_product_vector(self, product_id: str, vector: np.array):
        """Stores product vector in FAISS index."""
        self.index.add(np.array([vector], dtype=np.float32))

    def search_similar_products(self, vector: np.array, top_k: int = 5):
        """Finds top-K similar products using FAISS."""
        _, indices = self.index.search(np.array([vector], dtype=np.float32), top_k)
        return indices.tolist()