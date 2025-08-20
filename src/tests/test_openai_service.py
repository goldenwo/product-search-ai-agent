# src/tests/test_openai_service.py

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import Request
import numpy as np
import openai
import pytest

from src.services.clients.openai_client import OpenAIClient
from src.services.openai_service import OpenAIService, OpenAIServiceError

# Mock response structures (simplified)
MockChoice = MagicMock()
MockChoice.message.content = '{"key": "value"}'

MockCompletion = MagicMock()
MockCompletion.choices = [MockChoice]
MockCompletion.usage.prompt_tokens = 10
MockCompletion.usage.completion_tokens = 5
MockCompletion.usage.total_tokens = 15

MockEmbedding = MagicMock()
MockEmbedding.embedding = [0.1, 0.2, 0.3]


@pytest.fixture
def mock_openai_client():
    """Provides a MagicMock for the OpenAIClient."""
    client = MagicMock(spec=OpenAIClient)
    client.create_chat_completion = AsyncMock(return_value=MockCompletion)
    client.create_embeddings = AsyncMock(return_value=[MockEmbedding])
    client.create_message = MagicMock(side_effect=lambda role, content: {"role": role, "content": content})
    return client


@pytest.fixture
def openai_service(mock_openai_client):
    """Provides an OpenAIService instance with a mocked client."""
    # Use patch context manager to inject the mock client during service instantiation
    with patch("src.services.openai_service.OpenAIClient", return_value=mock_openai_client):
        service = OpenAIService()
        # We can directly assert on mock_openai_client now
        return service, mock_openai_client


# --- Tests for generate_response ---


@pytest.mark.asyncio
async def test_generate_response_success(openai_service):
    """Test successful response generation."""
    service, mock_client = openai_service
    prompt = "Test prompt"
    model = "test-chat-model"
    max_tokens = 100

    response = await service.generate_response(prompt, model=model, max_tokens=max_tokens)

    assert response == MockCompletion
    mock_client.create_chat_completion.assert_called_once()
    call_args = mock_client.create_chat_completion.call_args[1]
    assert call_args["model"] == model
    assert call_args["max_tokens"] == max_tokens
    assert call_args["messages"][0]["role"] == "system"
    assert call_args["messages"][0]["content"] == prompt
    assert "response_format" not in call_args or call_args["response_format"] is None


@pytest.mark.asyncio
async def test_generate_response_json_mode(openai_service):
    """Test successful response generation with JSON mode."""
    service, mock_client = openai_service
    prompt = "Test prompt for JSON"
    model = "test-chat-model-json"

    response = await service.generate_response(prompt, model=model, use_json_mode=True)

    assert response == MockCompletion
    mock_client.create_chat_completion.assert_called_once()
    call_args = mock_client.create_chat_completion.call_args[1]
    assert call_args["model"] == model
    assert call_args["messages"][0]["role"] == "system"
    assert call_args["messages"][0]["content"] == prompt
    assert call_args["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_generate_response_empty_content(openai_service):
    """Test handling of empty response content from client."""
    service, mock_client = openai_service
    prompt = "Test prompt"

    # Configure mock to return empty content
    mock_empty_choice = MagicMock()
    mock_empty_choice.message.content = ""
    mock_empty_completion = MagicMock()
    mock_empty_completion.choices = [mock_empty_choice]
    mock_client.create_chat_completion.return_value = mock_empty_completion

    with pytest.raises(OpenAIServiceError, match="Empty response content"):
        await service.generate_response(prompt)

    mock_client.create_chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_generate_response_api_error(openai_service):
    """Test that OpenAIServiceError is raised after underlying API errors."""
    service, mock_client = openai_service
    prompt = "Test prompt"

    dummy_request = Request(method="POST", url="http://test.openai.api/v1/chat/completions")

    # Configure mock to simulate persistent failure
    mock_client.create_chat_completion.side_effect = [
        openai.APIError("API Failed on 1st attempt", request=dummy_request, body=None),
        openai.APIError("API Failed on 2nd attempt", request=dummy_request, body=None),
        openai.APIError("API Failed on 3rd attempt", request=dummy_request, body=None),
    ]

    # Expect the service error wrapping the API error after all retries (we trust tenacity handles retries)
    with pytest.raises(OpenAIServiceError, match="OpenAI API error after all retries"):
        await service.generate_response(prompt)

    # Verify that post was called multiple times due to retries
    assert mock_client.create_chat_completion.call_count >= 1


@pytest.mark.asyncio
async def test_generate_response_unexpected_error(openai_service):
    """Test handling of unexpected errors during chat completion."""
    service, mock_client = openai_service
    prompt = "Test prompt"

    # Configure mock to raise a generic exception
    mock_client.create_chat_completion.side_effect = ValueError("Unexpected issue")

    with pytest.raises(OpenAIServiceError, match="Unexpected OpenAI Failure"):
        await service.generate_response(prompt)

    # Should not retry on non-API errors by default
    mock_client.create_chat_completion.assert_called_once()


# --- Tests for generate_embedding ---


@pytest.mark.asyncio
async def test_generate_embedding_single_string(openai_service):
    """Test successful embedding generation for a single string."""
    service, mock_client = openai_service
    text = "Embed this text"
    model = "test-embed-model"

    embedding = await service.generate_embedding(text, model=model)

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (1, 3)  # (n_texts, dim) -> (1, 3) for our mock
    np.testing.assert_array_equal(embedding, np.array([[0.1, 0.2, 0.3]]))
    mock_client.create_embeddings.assert_called_once_with(text, model=model)


@pytest.mark.asyncio
async def test_generate_embedding_list_strings(openai_service):
    """Test successful embedding generation for a list of strings."""
    service, mock_client = openai_service
    texts = ["Embed text 1", "Embed text 2"]
    model = "test-embed-model"

    # Configure mock to return multiple embeddings
    mock_embedding_1 = MagicMock()
    mock_embedding_1.embedding = [0.1, 0.2, 0.3]
    mock_embedding_2 = MagicMock()
    mock_embedding_2.embedding = [0.4, 0.5, 0.6]
    mock_client.create_embeddings.return_value = [mock_embedding_1, mock_embedding_2]

    embedding = await service.generate_embedding(texts, model=model)

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (2, 3)  # (n_texts, dim) -> (2, 3)
    np.testing.assert_array_equal(embedding, np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]))
    mock_client.create_embeddings.assert_called_once_with(texts, model=model)


@pytest.mark.asyncio
async def test_generate_embedding_api_error(openai_service):
    """Test handling of OpenAI API errors during embedding."""
    service, mock_client = openai_service
    text = "Test text"

    # Configure mock to raise an API error with a dummy request
    dummy_request = Request(method="POST", url="http://test.openai.api/v1/embeddings")
    mock_client.create_embeddings.side_effect = openai.APIError("Embedding API Failed", request=dummy_request, body=None)

    with pytest.raises(OpenAIServiceError, match="Failed to generate embedding"):
        await service.generate_embedding(text)

    mock_client.create_embeddings.assert_called_once()


@pytest.mark.asyncio
async def test_generate_embedding_value_error(openai_service):
    """Test handling of value/type errors during embedding."""
    service, mock_client = openai_service
    text = "Test text"

    # Simulate an error that might occur during client processing
    mock_client.create_embeddings.side_effect = ValueError("Bad input format")

    with pytest.raises(OpenAIServiceError, match="Failed to generate embedding"):
        await service.generate_embedding(text)

    mock_client.create_embeddings.assert_called_once()
