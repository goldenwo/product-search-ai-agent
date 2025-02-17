"""OpenAI service for generating AI responses and embeddings for product search."""

import numpy as np
import openai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from src.utils import OpenAIServiceError, logger
from src.utils.config import OPENAI_API_KEY


class OpenAIService:
    """
    Handles interactions with OpenAI API for AI-powered query parsing.
    """

    def __init__(self):
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)  # Load API key

    @retry(
        stop=stop_after_attempt(3),  # Retry 3 times
        wait=wait_fixed(2),  # Wait 2 seconds between retries
        retry=retry_if_exception_type(openai.OpenAIError),  # Retry only OpenAI errors
    )
    def generate_response(self, prompt: str) -> str:
        """
        Generates a response from OpenAI. Retries on failure.
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
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

    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding vector for text using OpenAI's embedding model."""
        try:
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8191],  # OpenAI has a token limit
            )
            return np.array(response.data[0].embedding)
        except (openai.OpenAIError, ValueError, TypeError) as e:
            logger.error("❌ Error generating embedding: %s", str(e))
            raise OpenAIServiceError("Failed to generate embedding") from e
