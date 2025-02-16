"""Test the QueryParser class."""

from unittest.mock import patch

import pytest

from src.ai_agent.query_parser import QueryParser


@pytest.fixture
def query_parser():
    """
    Returns an instance of QueryParser.
    """
    return QueryParser()


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_success(mock_openai, parser):
    """Test successful attribute extraction."""
    mock_openai.return_value = '{"category": "electronics", "brand": "Sony", "budget": "500"}'

    attributes = parser.extract_product_attributes("Sony TV under $500")

    assert isinstance(attributes, dict)
    assert attributes["category"] == "electronics"
    assert attributes["brand"] == "Sony"
    assert attributes["budget"] == "500"


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes_invalid_json(mock_openai, parser):
    """Test handling of invalid JSON response."""
    mock_openai.return_value = "invalid json"

    attributes = parser.extract_product_attributes("test query")
    assert "error" in attributes


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_for_store_success(mock_openai, parser):
    """Test query refinement for specific store."""
    mock_openai.return_value = '{"keywords": "gaming laptop", "category": "computers"}'

    refined = parser.refine_query_for_store("gaming laptop", "Amazon")
    assert isinstance(refined, dict)
    assert "keywords" in refined


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_refine_query_fallback(mock_openai, parser):
    """Test fallback behavior for query refinement."""
    mock_openai.side_effect = Exception("API Error")

    refined = parser.refine_query_for_store("test query", "Amazon")
    assert refined == {"keywords": "test query"}
