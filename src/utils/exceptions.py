"""Custom exceptions for AI-powered product search."""


class OpenAIServiceError(Exception):
    """
    Exception raised for OpenAI API failures.

    Attributes:
        message: Error message
        status_code: Optional HTTP status code
    """


class StoreAPIError(Exception):
    """
    Exception raised for store API failures.

    Attributes:
        store: Name of store that failed
        message: Error message
        status_code: HTTP status code
    """


class FAISSIndexError(Exception):
    """
    Exception raised for FAISS vector search failures.

    Attributes:
        message: Error message
        index_size: Optional size of index when error occurred
    """
