"""FAISS service for efficient similarity search of product vectors."""

from typing import Any, List, Optional

import faiss
import numpy as np

from src.utils import FAISSIndexError, logger
from src.utils.config import FAISS_VECTOR_DIMENSION


class FAISSService:
    """
    Service for vector similarity search using FAISS.

    Attributes:
        vector_dimension: Dimension of embedding vectors
        index: FAISS index for similarity search
    """

    def __init__(self, vector_dimension: Optional[int] = None):
        """
        Initialize FAISS index.

        Args:
            vector_dimension: Optional dimension override (defaults to config)

        Raises:
            FAISSIndexError: If index initialization fails
        """
        self.vector_dimension = vector_dimension or FAISS_VECTOR_DIMENSION
        try:
            self.index: Any = faiss.IndexFlatL2(self.vector_dimension)
        except Exception as e:
            logger.error("❌ FAISS index initialization failed: %s", str(e))
            raise FAISSIndexError("Failed to initialize FAISS index") from e

    def add_vectors(self, vectors: np.ndarray) -> None:
        """
        Add vectors to FAISS index.

        Args:
            vectors: Array of vectors to add, shape (n_vectors, vector_dimension)

        Raises:
            FAISSIndexError: If vectors have wrong dimension or addition fails
            ValueError: If vectors array is empty
        """
        if vectors.size == 0:
            raise ValueError("Empty vector array")

        if vectors.shape[1] != self.vector_dimension:
            raise FAISSIndexError(f"FAISS expects {self.vector_dimension}-dimensional vectors")

        try:
            vectors_f32: np.ndarray = vectors.astype(np.float32)
            self.index.add(vectors_f32)  # pylint: disable=E1120
        except Exception as e:
            logger.error("❌ Failed to add vectors to FAISS: %s", str(e))
            raise FAISSIndexError("Failed to add vectors to index") from e

    def search_similar(self, query_vector: np.ndarray, k: int = 5) -> List[int]:
        """
        Search for k most similar vectors.

        Args:
            query_vector: Query vector, shape (vector_dimension,)
            k: Number of similar vectors to return

        Returns:
            List[int]: Indices of k most similar vectors

        Raises:
            FAISSIndexError: If search fails or vector has wrong dimension
        """
        if query_vector.shape != (self.vector_dimension,):
            raise FAISSIndexError(f"Query vector must be {self.vector_dimension}-dimensional")

        try:
            query_f32: np.ndarray = query_vector.reshape(1, -1).astype(np.float32)
            _distances, indices = self.index.search(query_f32, k)  # pylint: disable=E1120
            return indices[0].tolist()
        except Exception as e:
            logger.error("❌ FAISS search failed: %s", str(e))
            raise FAISSIndexError("Failed to perform similarity search") from e

    def __del__(self):
        """Clean up FAISS index when service is destroyed."""
        if hasattr(self, "index"):
            self.index.reset()  # Clear the index
