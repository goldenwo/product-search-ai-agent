"""Custom exceptions for AI-powered product search."""


class OpenAIServiceError(Exception):
    """
    Exception raised for OpenAI API failures.

    Attributes:
        message: Error message
        status_code: Optional HTTP status code
    """

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class SerpAPIException(Exception):
    """
    Exception raised for SERP API failures.

    Attributes:
        message: Error message
        store: Service identifier (e.g., 'serp', 'google-shopping')
        status_code: HTTP status code
    """

    def __init__(self, message: str, store: str, status_code: int = 500):
        self.message = message
        self.store = store
        self.status_code = status_code
        super().__init__(f"{store} API error: {message}")
