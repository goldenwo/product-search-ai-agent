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
        """Uses AI to determine the best stores for the given product attributes."""
        available_stores = [config["name"] for config in self.store_config.store_configs.values()]
        if not available_stores:
            return []

        prompt = f"""You are a retail expert. Select the most suitable stores for this purchase:

        Product Attributes: {attributes}
        Available Stores: {available_stores}

        RULES:
        1. Return ONLY a JSON array of store names
        2. Consider these factors in order:
           - Category match (e.g., electronics → BestBuy)
           - Price tier alignment (e.g., budget → Amazon)
           - Product type support (e.g., digital → Steam)
           - Brand availability
        3. Limit selection to up to 10 most relevant stores
        4. Include at least one general retailer if unsure
        5. Only use stores from the available list

        Example inputs and outputs:
        Input: {{"category": "electronics", "price_range": "premium", "brand_specific": "yes"}}
        Output: ["BestBuy", "Amazon"]

        Input: {{"category": "clothing", "price_range": "luxury", "brand_specific": "no"}}
        Output: ["Nordstrom", "Amazon"]
        """

        logger.info("🔍 Selecting stores for attributes: %s", attributes)

        try:
            ai_response = self.openai_service.generate_response(prompt)
            selected_stores = json.loads(ai_response)

            # Filter to only include valid stores
            valid_stores = [store for store in selected_stores if store in available_stores]

            if valid_stores:
                logger.info("✅ Selected stores: %s", valid_stores)
                return valid_stores

        except (json.JSONDecodeError, OpenAIServiceError) as e:
            logger.error("❌ Error selecting stores: %s", str(e))

        return available_stores
