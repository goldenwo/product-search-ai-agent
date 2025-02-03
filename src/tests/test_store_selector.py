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
def test_select_best_stores(mock_openai, store_selector):
    """
    Test if AI selects the best stores using a mocked OpenAI response.
    """
    # Mock AI response
    mock_openai.return_value = '["Amazon", "BestBuy"]'

    attributes = {"category": "electronics", "brand": "Sony"}
    selected_stores = store_selector.select_best_stores(attributes)

    assert isinstance(selected_stores, list)
    assert "Amazon" in selected_stores
    assert "BestBuy" in selected_stores
    mock_openai.assert_called_once()  # Ensure AI was called once
