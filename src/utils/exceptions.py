class OpenAIServiceError(Exception):
    """Exception for OpenAI service-related errors."""


class StoreAPIError(Exception):
    """Exception for external store API failures."""


class FAISSIndexError(Exception):
    """Exception for FAISS vector search errors."""
