"""OpenAI service for generating AI responses and embeddings for product search."""

from typing import List, Optional, Union

import numpy as np
import openai
from openai.types.chat import ChatCompletion
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from src.services.clients.openai_client import OpenAIClient
from src.utils import OpenAIServiceError, logger
from src.utils.config import OPENAI_CHAT_MODEL, OPENAI_EMBEDDING_MODEL


class OpenAIService:
    """
    Handles interactions with OpenAI API for AI-powered tasks.

    Provides a business logic layer on top of OpenAI API interactions,
    including retries, error handling, and response processing.
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
        retry=retry_if_exception_type(openai.OpenAIError),  # Retry only OpenAI API errors
    )
    def generate_response(self, prompt: str, model: str = OPENAI_CHAT_MODEL, max_tokens: int = 1500, use_json_mode: bool = False) -> ChatCompletion:
        """
        Generates a response from OpenAI's chat completion API. Retries on failure.

        Args:
            prompt: Text prompt to send to the model (acts as system message).
            model: OpenAI model identifier.
            max_tokens: Maximum tokens for the response.
            use_json_mode: If True, request JSON output from the model.

        Returns:
            openai.ChatCompletion: The full response object from the API, including usage data.

        Raises:
            OpenAIServiceError: If the API call fails after retries
        """
        try:
            # IMPORTANT: For JSON mode, the prompt MUST instruct the model to produce JSON.
            # The API enforces this. Ensure prompts used with this flag meet this requirement.
            messages = [self.client.create_message(role="system", content=prompt)]

            # Set response_format if JSON mode requested
            response_format_arg = {"type": "json_object"} if use_json_mode else None

            response = self.client.create_chat_completion(
                messages=messages, model=model, temperature=0.2, max_tokens=max_tokens, response_format=response_format_arg
            )
            if not response.choices or not response.choices[0].message.content:
                raise OpenAIServiceError("Empty response content from OpenAI")
            return response

        except openai.OpenAIError as e:
            logger.error("❌ OpenAI API returned an error: %s", e)
            raise OpenAIServiceError("OpenAI API error") from e

        except Exception as e:
            logger.error("❌ Unexpected OpenAI error: %s", e)
            raise OpenAIServiceError("Unexpected OpenAI Failure") from e

    def generate_embedding(self, text: Union[str, List[str]], model: str = OPENAI_EMBEDDING_MODEL) -> np.ndarray:
        """
        Generate embedding vector(s) for text using OpenAI's embedding model.

        Args:
            text: Single text string or list of text strings to embed.
            model: OpenAI embedding model identifier.

        Returns:
            Numpy array of shape (n_texts, embedding_dim).

        Raises:
            OpenAIServiceError: If the API call fails
        """
        try:
            # Get embeddings from the client
            embeddings = self.client.create_embeddings(text, model=model)
            # Always return 2D array of shape (n_texts, embedding_dim)
            return np.array([item.embedding for item in embeddings])

        except (openai.OpenAIError, ValueError, TypeError) as e:
            logger.error("❌ Error generating embedding: %s", e)
            raise OpenAIServiceError("Failed to generate embedding") from e
