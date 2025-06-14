"""Client for interacting with OpenAI APIs."""

from typing import Dict, List, Literal, Optional, Union

import openai
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_assistant_message_param import ChatCompletionAssistantMessageParam
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import ChatCompletionSystemMessageParam
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam
from openai.types.embedding import Embedding

from src.utils import logger
from src.utils.config import OPENAI_API_KEY


class OpenAIClient:
    """
    Low-level client for making requests to OpenAI APIs.

    Handles raw API interactions including request formatting,
    authentication, and basic error handling. Should be used
    by a higher-level service (e.g., OpenAIService) which adds
    business logic like retries, response parsing, etc.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenAI API client.

        Args:
            api_key: Optional API key override
        """
        self.api_key = api_key or OPENAI_API_KEY
        self.client = openai.OpenAI(api_key=self.api_key)

        if not self.api_key:
            logger.warning("⚠️ No OpenAI API key provided. API calls will fail.")

    @staticmethod
    def create_message(role: Literal["system", "user", "assistant"], content: str) -> ChatCompletionMessageParam:
        """
        Create a properly typed message object for the OpenAI Chat Completion API.

        Args:
            role: Message role ('system', 'user', or 'assistant')
            content: Message content

        Returns:
            ChatCompletionMessageParam: Properly typed message
        """
        if role == "system":
            return ChatCompletionSystemMessageParam(role=role, content=content)
        elif role == "user":
            return ChatCompletionUserMessageParam(role=role, content=content)
        elif role == "assistant":
            return ChatCompletionAssistantMessageParam(role=role, content=content)
        else:
            # This shouldn't happen due to the Literal type constraint,
            # but provides a fallback just in case.
            logger.warning("Invalid role '%s' provided to create_message, defaulting to 'user'.", role)
            return ChatCompletionUserMessageParam(role="user", content=content)

    def create_chat_completion(
        self,
        messages: List[ChatCompletionMessageParam],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 100,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> ChatCompletion:
        """
        Create a chat completion via OpenAI API.

        Args:
            messages: List of properly typed message objects
            model: OpenAI model to use
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            response_format: Optional dictionary to specify response format (e.g., { "type": "json_object" })
            **kwargs: Additional parameters to pass to the API

        Returns:
            ChatCompletion: The full API response object, including usage data.

        Raises:
            openai.OpenAIError: If the API call fails
        """
        try:
            # Construct arguments, adding response_format only if provided
            api_args = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs,
            }
            if response_format:
                api_args["response_format"] = response_format

            # Return the full response object
            response = self.client.chat.completions.create(**api_args)
            return response
        except openai.OpenAIError as e:
            logger.error("❌ OpenAI chat completion API error: %s", e)
            raise

    def create_embeddings(self, texts: Union[str, List[str]], model: str = "text-embedding-3-small") -> List[Embedding]:
        """
        Create embeddings via OpenAI API.

        Args:
            texts: Text or list of texts to embed
            model: OpenAI embedding model to use

        Returns:
            List[Embedding]: Raw API response embeddings

        Raises:
            openai.OpenAIError: If the API call fails
        """
        try:
            # Convert single string to list for consistent handling
            input_texts = [texts] if isinstance(texts, str) else texts

            response = self.client.embeddings.create(
                model=model,
                input=input_texts,
            )
            return response.data
        except openai.OpenAIError as e:
            logger.error("❌ OpenAI embeddings API error: %s", e)
            raise
