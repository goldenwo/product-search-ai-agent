import pytest
from unittest.mock import patch
from src.ai_agent.query_parser import QueryParser

@pytest.fixture
def query_parser():
    """
    Returns an instance of QueryParser.
    """
    return QueryParser()

@patch("src.services.openai_service.OpenAIService.generate_response")
def test_extract_product_attributes(mock_openai, query_parser):
    """
    Test if AI correctly extracts product attributes using a mocked OpenAI response.
    """
    # Mock AI response
    mock_openai.return_value = '{"category": "electronics", "brand": "Sony", "budget": "500"}'

    query = "best 4K gaming monitor under $500"
    attributes = query_parser.extract_product_attributes(query)

    assert isinstance(attributes, dict)
    assert attributes["category"] == "electronics"
    assert attributes["brand"] == "Sony"
    assert attributes["budget"] == "500"
    mock_openai.assert_called_once()  # Ensure AI was called once
