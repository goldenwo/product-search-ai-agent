"""Store selector service that uses AI to choose the most relevant stores for a product search."""

import json
from typing import Dict, List

from src.services.openai_service import OpenAIService
from src.utils import OpenAIServiceError, logger
from src.utils.store_config import StoreConfig


class StoreSelector:
    """
    AI-powered store selector that determines the best online stores
    based on product attributes.
    """

    def __init__(self):
        self.openai_service = OpenAIService()  # Load AI model
        self.store_config = StoreConfig()

    def select_best_stores(self, attributes: Dict[str, str]) -> List[str]:
        """
        Uses AI to determine the best stores for the given product attributes.

        Args:
            attributes (dict): Extracted attributes from the search query.

        Returns:
            List[str]: A list of the best online stores for the product.
        """
        available_stores = [config["name"] for config in self.store_config.store_configs.values()]

        prompt = f"""
        Given the following product attributes: {attributes},
        which online stores from this list are most suitable for purchasing this product?
        Stores available: {available_stores}.
        Return a JSON list of store names (e.g., ["Amazon", "BestBuy"]).
        """

        logger.info("🔍 Selecting stores for attributes: %s", attributes)

        # Use AI to determine the best stores
        # Extract store list from AI response
        try:
            ai_response = self.openai_service.generate_response(prompt)
            selected_stores = json.loads(ai_response)  # Convert string output to a list
            if isinstance(selected_stores, list) and all(store in available_stores for store in selected_stores):
                logger.info("✅ AI selected stores: %s", selected_stores)
                return selected_stores
        except OpenAIServiceError as e:
            logger.error("❌ Error selecting stores: %s", e)

        # Default: Use all stores if AI response is invalid
        return available_stores
