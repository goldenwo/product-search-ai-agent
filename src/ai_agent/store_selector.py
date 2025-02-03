from typing import Dict, List

from src.services.openai_service import OpenAIService
from src.utils import logger
from src.utils.config import STORE_APIS


class StoreSelector:
    """
    AI-powered store selector that determines the best online stores
    based on product attributes.
    """

    def __init__(self):
        self.openai_service = OpenAIService()  # Load AI model

    def select_best_stores(self, attributes: Dict[str, str]) -> List[str]:
        """
        Uses AI to determine the best stores for the given product attributes.

        Args:
            attributes (dict): Extracted attributes from the search query.

        Returns:
            List[str]: A list of the best online stores for the product.
        """
        prompt = f"""
        Given the following product attributes: {attributes},
        which online stores from this list are most suitable for purchasing this product?
        Stores available: {list(STORE_APIS.keys())}.
        Return a JSON list of store names (e.g., ["Amazon", "BestBuy"]).
        """

        logger.info(f"🔍 Selecting stores for attributes: {attributes}")

        # Use AI to determine the best stores
        ai_response = self.openai_service.generate_response(prompt)

        # Extract store list from AI response
        try:
            selected_stores = eval(ai_response)  # Convert string output to a list
            if isinstance(selected_stores, list) and all(store in STORE_APIS for store in selected_stores):
                logger.info(f"✅ AI selected stores: {selected_stores}")
                return selected_stores
        except Exception as e:
            logger.error(f"❌ Error selecting stores: {e}")

        # Default: Use all stores if AI response is invalid
        return list(STORE_APIS.keys())
