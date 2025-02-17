"""Module for parsing natural language queries into structured product attributes using AI."""

import json
from typing import Dict

from src.services.openai_service import OpenAIService
from src.utils import OpenAIServiceError, logger
from src.utils.store_config import StoreConfig


class QueryParser:
    """
    AI-powered query parser that extracts structured product attributes
    from a user's natural language query.
    """

    def __init__(self):
        self.openai_service = OpenAIService()  # Load AI model
        self.store_config = StoreConfig()

    def extract_product_attributes(self, query: str) -> Dict[str, str]:
        """
        Uses AI to extract structured product attributes from a search query.

        Args:
            query (str): The user's raw search query.

        Returns:
            Dict[str, str]: Extracted attributes (e.g., category, brand, budget).
        """
        if not query.strip():
            logger.error("❌ Empty query provided")
            return {"error": "Empty query"}

        prompt = f"""
        Extract key product attributes from the following search query:
        "{query}"
        
        Return the attributes as a JSON dictionary with keys like 'category', 'brand', 
        'budget', 'size', 'color', etc. Example output:
        {{"category": "electronics", "brand": "Sony", "budget": "500"}}
        """
        logger.info("🔍 Processing user query: %s", query)

        try:
            ai_response = self.openai_service.generate_response(prompt)
            attributes = json.loads(ai_response)  # Convert AI output to dict
            if isinstance(attributes, dict):
                logger.info("✅ Extracted attributes: %s", attributes)
                return attributes
            else:
                logger.error("❌ AI response was not a dictionary: %s", ai_response)
                return {"error": "Invalid AI response format"}
        except OpenAIServiceError as e:
            logger.error("❌ OpenAI service error: %s", e)
            return {"error": f"AI Service Error: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error("❌ Error decoding JSON response: %s", str(e))
            return {"error": f"JSON Error: {str(e)}"}

    def refine_query_for_store(self, query: str, store: str) -> Dict[str, str]:
        """
        Refines the search query for a specific store's API format.
        """
        if not query.strip():
            logger.error("❌ Empty query provided")
            return {"keywords": ""}

        if not store.strip():
            logger.error("❌ Empty store name provided")
            return {"keywords": query}

        allowed_params = self.store_config.get_allowed_params(store)

        prompt = f"""
        Refine this search query: "{query}"
        for the {store} store API. Only use these allowed parameters: {allowed_params}.
        Return as JSON with parameters matching the store's API exactly.
        Example: {{"keywords": "blue shoes", "category": "footwear"}}
        """

        try:
            ai_response = self.openai_service.generate_response(prompt)
            refined_query = json.loads(ai_response)

            # Validate and filter parameters
            validated_query = {k: str(v) for k, v in refined_query.items() if k in allowed_params}

            if not validated_query:
                return {"keywords": query}  # Fallback to simple search

            logger.info("✅ Refined query for %s: %s", store, validated_query)
            return validated_query

        except (OpenAIServiceError, json.JSONDecodeError) as e:
            logger.error("❌ Error refining query: %s", e)
            return {"keywords": query}  # Fallback to basic query
