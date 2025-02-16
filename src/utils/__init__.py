"""
Utility functions and configurations for the AI-powered product search system.
"""

from .config import (
    FAISS_VECTOR_DIMENSION,
    OPENAI_API_KEY,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_TTL,
)
from .exceptions import FAISSIndexError, OpenAIServiceError, StoreAPIError
from .logging import logger

__all__ = [
    "FAISS_VECTOR_DIMENSION",
    "OPENAI_API_KEY",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_TTL",
    "logger",
    "OpenAIServiceError",
    "StoreAPIError",
    "FAISSIndexError",
]
