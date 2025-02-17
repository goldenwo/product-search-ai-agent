"""Test the StoreSelector class."""

from unittest.mock import patch

import pytest

from src.ai_agent.store_selector import StoreSelector
from src.utils import OpenAIServiceError


@pytest.fixture
def store_selector():
    """
    Returns an instance of StoreSelector.
    """
    selector = StoreSelector()
    # Mock the store configs
    selector.store_config.store_configs = {
        "amazon": {
            "name": "Amazon",
            "api_url": "https://api.amazon.com",
            "api_key": "test-key",
            "timeout": 5,
            "allowed_params": ["keywords", "category"],
        },
        "bestbuy": {
            "name": "BestBuy",
            "api_url": "https://api.bestbuy.com",
            "api_key": "test-key",
            "timeout": 5,
            "allowed_params": ["keywords", "category"],
        },
    }
    return selector


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_success(mock_openai, store_selector):  # pylint: disable=redefined-outer-name
    """Test successful store selection."""
    mock_openai.return_value = '["Amazon", "BestBuy"]'

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert "Amazon" in stores
    assert "BestBuy" in stores
    assert len(stores) == 2


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_invalid_response(mock_openai, store_selector):  # pylint: disable=redefined-outer-name
    """Test handling of invalid AI response."""
    mock_openai.return_value = "invalid json"

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert len(stores) > 0  # Should return all available stores as fallback


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_api_error(mock_openai, store_selector):  # pylint: disable=redefined-outer-name
    """Test handling of API errors."""
    mock_openai.side_effect = OpenAIServiceError("API Error")

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert len(stores) > 0  # Should return all available stores as fallback


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_empty_attributes(mock_openai, store_selector):  # pylint: disable=redefined-outer-name
    """Test handling of empty attributes."""
    mock_openai.return_value = '["Amazon", "BestBuy"]'  # Return default stores

    stores = store_selector.select_best_stores({})
    assert isinstance(stores, list)
    assert len(stores) > 0  # Should return all available stores


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_invalid_store_names(mock_openai, store_selector):  # pylint: disable=redefined-outer-name
    """Test handling of invalid store names in AI response."""
    mock_openai.return_value = '["InvalidStore1", "InvalidStore2"]'

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert len(stores) > 0  # Should return all available stores as fallback


@patch("src.services.openai_service.OpenAIService.generate_response")
def test_select_best_stores_partial_valid_stores(mock_openai, store_selector):  # pylint: disable=redefined-outer-name
    """Test handling of partially valid store names."""
    mock_openai.return_value = '["Amazon", "InvalidStore"]'

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert "Amazon" in stores
    assert len(stores) == 1  # Should only include valid store


def test_select_best_stores_no_config(store_selector):  # pylint: disable=redefined-outer-name
    """Test handling of missing store configuration."""
    store_selector.store_config.store_configs = {}

    stores = store_selector.select_best_stores({"category": "electronics"})
    assert isinstance(stores, list)
    assert len(stores) == 0  # Should return empty list when no stores configured
