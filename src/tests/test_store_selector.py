"""Test the StoreSelector class."""

from unittest.mock import patch

import pytest

from src.ai_agent.store_selector import StoreSelector


@pytest.fixture
def store_selector():
    """
    Returns an instance of StoreSelector.
    """
    return StoreSelector()


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_success(mock_openai, store_selector):
    """Test successful store selection."""
    mock_openai.return_value = '["Amazon", "BestBuy"]'

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert "Amazon" in stores
    assert "BestBuy" in stores


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_invalid_response(mock_openai, store_selector):
    """Test handling of invalid AI response."""
    mock_openai.return_value = "invalid json"

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert len(stores) > 0  # Should return all available stores as fallback


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_api_error(mock_openai, store_selector):
    """Test handling of API errors."""
    mock_openai.side_effect = Exception("API Error")

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert len(stores) > 0  # Should return all available stores as fallback


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_empty_attributes(mock_openai, store_selector):
    """Test handling of empty attributes."""
    stores = store_selector.select_best_stores({})
    assert isinstance(stores, list)
    assert len(stores) > 0  # Should return all available stores
