"""Test the QueryParser class."""

from unittest.mock import Mock, patch

import pytest

from src.ai_agent.query_parser import QueryParser
from src.utils import OpenAIServiceError


@pytest.fixture
def query_parser():
    """
    Returns an instance of QueryParser.
    """
    parser = QueryParser()
    # Mock the entire store_config object
    parser.store_config = Mock()
    parser.store_config.get_allowed_params.return_value = ["keywords", "category"]
    return parser


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_success(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test successful attribute extraction."""
    mock_openai.return_value = '{"category": "electronics", "brand": "Sony", "budget": "500"}'

    attributes = query_parser.extract_product_attributes("Sony TV under $500")

    assert isinstance(attributes, dict)
    assert attributes["category"] == "electronics"
    assert attributes["brand"] == "Sony"
    assert attributes["budget"] == "500"


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_invalid_json(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of invalid JSON response."""
    mock_openai.return_value = "invalid json"

    attributes = query_parser.extract_product_attributes("test query")
    assert isinstance(attributes, dict)
    assert "error" in attributes


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_empty_query(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of empty query."""
    # Don't call OpenAI for empty query
    mock_openai.assert_not_called()

    attributes = query_parser.extract_product_attributes("")
    assert isinstance(attributes, dict)
    assert "error" in attributes


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_api_error(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of OpenAI API error."""
    mock_openai.side_effect = OpenAIServiceError("API Error")

    attributes = query_parser.extract_product_attributes("test query")
    assert isinstance(attributes, dict)
    assert "error" in attributes


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_success(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test successful query refinement for store."""
    mock_openai.return_value = '{"keywords": "gaming laptop", "category": "computers"}'

    refined = query_parser.refine_query_for_store("gaming laptop", "Amazon")
    assert isinstance(refined, dict)
    assert "keywords" in refined
    assert "category" in refined
    assert refined["keywords"] == "gaming laptop"
    assert refined["category"] == "computers"


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_invalid_json(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of invalid JSON in store refinement."""
    mock_openai.return_value = "invalid json"

    refined = query_parser.refine_query_for_store("test query", "Amazon")
    assert isinstance(refined, dict)
    assert refined == {"keywords": "test query"}  # Fallback to original query


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_empty_query(_mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of empty query in store refinement."""
    refined = query_parser.refine_query_for_store("", "Amazon")
    assert isinstance(refined, dict)
    assert refined == {"keywords": ""}


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_empty_store(_mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of empty store name."""
    refined = query_parser.refine_query_for_store("test query", "")
    assert isinstance(refined, dict)
    assert refined == {"keywords": "test query"}


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_api_error(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of OpenAI API error in store refinement."""
    mock_openai.side_effect = OpenAIServiceError("API Error")

    refined = query_parser.refine_query_for_store("test query", "Amazon")
    assert isinstance(refined, dict)
    assert refined == {"keywords": "test query"}


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_invalid_params(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of invalid parameters in AI response."""
    mock_openai.return_value = '{"invalid_param": "value"}'

    refined = query_parser.refine_query_for_store("test query", "Amazon")
    assert isinstance(refined, dict)
    assert refined == {"keywords": "test query"}
