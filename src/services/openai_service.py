"""OpenAI service for generating AI responses and embeddings for product search."""

from typing import List, Optional, Union

import numpy as np
import openai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from src.services.clients.openai_client import OpenAIClient
from src.utils import OpenAIServiceError, logger


class OpenAIService:
    """
    Handles interactions with OpenAI API for AI-powered query parsing.

    Provides business logic layer on top of OpenAI API interactions,
    including retries, error handling, and data normalization.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenAI service with API client.

        Args:
            api_key: Optional API key override
        """
        self.client = OpenAIClient(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),  # Retry 3 times
        wait=wait_fixed(2),  # Wait 2 seconds between retries
        retry=retry_if_exception_type(openai.OpenAIError),  # Retry only OpenAI errors
    )
    def generate_response(self, prompt: str, model: str = "gpt-4o-mini") -> str:
        """
        Generates a response from OpenAI. Retries on failure.

        Args:
            prompt: Text prompt to send to the model
            model: OpenAI model to use

        Returns:
            str: Generated text response

        Raises:
            OpenAIServiceError: If the API call fails after retries
        """
        try:
            messages = [self.client.create_message(role="system", content=prompt)]
            response = self.client.create_chat_completion(
                messages=messages,
                model=model,
                temperature=0.7,
                max_tokens=100,
            )
            content = response.choices[0].message.content
            if not content:
                raise OpenAIServiceError("Empty response from OpenAI")
            return content

        except openai.OpenAIError as e:
            logger.error("❌ OpenAI API returned an error: %s", str(e))
            raise OpenAIServiceError("OpenAI API error") from e

        except Exception as e:
            logger.error("❌ Unexpected OpenAI error: %s", str(e))
            raise OpenAIServiceError("Unexpected OpenAI Failure") from e

    def generate_embedding(self, text: Union[str, List[str]], model: str = "text-embedding-3-small") -> np.ndarray:
        """
        Generate embedding vector(s) for text using OpenAI's embedding model.

        Args:
            text: Single text or list of texts to embed
            model: OpenAI embedding model to use

        Returns:
            np.ndarray: Array of shape (n_texts, embedding_dim)

        Raises:
            OpenAIServiceError: If the API call fails
        """
        try:
            # Get embeddings from the client
            embeddings = self.client.create_embeddings(text, model=model)
            # Always return 2D array of shape (n_texts, embedding_dim)
            return np.array([item.embedding for item in embeddings])

        except (openai.OpenAIError, ValueError, TypeError) as e:
            logger.error("❌ Error generating embedding: %s", str(e))
            raise OpenAIServiceError("Failed to generate embedding") from e
