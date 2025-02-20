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
    parser.store_config.get_allowed_params.return_value = ["categoryId", "price.min", "price.max"]
    return parser


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_success(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test successful attribute extraction with all valid fields."""
    mock_openai.return_value = '{"category": "shoes", "brand": "nike", "color": "red", "budget": "100"}'

    attributes = query_parser.extract_product_attributes("red nike shoes under $100")

    assert isinstance(attributes, dict)
    assert attributes["category"] == "shoes"
    assert attributes["brand"] == "nike"
    assert attributes["color"] == "red"
    assert attributes["budget"] == "100"
    assert len(attributes) == 4  # Only specified attributes


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_partial_match(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test extraction with only some attributes found."""
    mock_openai.return_value = '{"category": "electronics", "brand": "sony"}'

    attributes = query_parser.extract_product_attributes("sony tv")

    assert isinstance(attributes, dict)
    assert attributes["category"] == "electronics"
    assert attributes["brand"] == "sony"
    assert "color" not in attributes
    assert "budget" not in attributes
    assert len(attributes) == 2


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_invalid_json(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of invalid JSON response."""
    mock_openai.return_value = "invalid json"

    attributes = query_parser.extract_product_attributes("test query")
    assert isinstance(attributes, dict)
    assert "error" in attributes


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_non_dict_response(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of non-dictionary response."""
    mock_openai.return_value = '["not", "a", "dictionary"]'

    attributes = query_parser.extract_product_attributes("test query")
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
    """Test successful query refinement with all allowed parameters."""
    mock_openai.return_value = '{"categoryId": "abcat0502000", "price.min": "800", "price.max": "1000"}'

    refined = query_parser.refine_query_for_store("gaming laptop under $1000", "BestBuy")

    assert isinstance(refined, dict)
    assert refined["categoryId"] == "abcat0502000"
    assert refined["price.min"] == "800"
    assert refined["price.max"] == "1000"
    assert len(refined) == 3  # Only allowed parameters


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_non_string_values(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of non-string values in response."""
    mock_openai.return_value = '{"categoryId": "abcat0502000", "price.max": 1000}'

    refined = query_parser.refine_query_for_store("laptop under 1000", "BestBuy")
    assert isinstance(refined, dict)
    assert isinstance(refined["price.max"], str)  # Should convert to string


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_invalid_json(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of invalid JSON in store refinement."""
    mock_openai.return_value = "invalid json"

    refined = query_parser.refine_query_for_store("test query", "BestBuy")
    assert refined is None  # Should return None, not empty dict


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_empty_store(_mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of empty store name."""
    refined = query_parser.refine_query_for_store("test query", "")
    assert refined is None


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_api_error(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of OpenAI API error in store refinement."""
    mock_openai.side_effect = OpenAIServiceError("API Error")

    refined = query_parser.refine_query_for_store("test query", "BestBuy")
    assert refined is None


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_invalid_params(mock_openai, query_parser):  # pylint: disable=redefined-outer-name
    """Test handling of invalid parameters in AI response."""
    mock_openai.return_value = '{"invalid_param": "value"}'

    refined = query_parser.refine_query_for_store("test query", "BestBuy")
    assert refined is None  # Should return None when no valid params
