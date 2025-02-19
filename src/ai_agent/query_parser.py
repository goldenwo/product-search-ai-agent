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
        Extracts key product attributes that help determine the best stores for a query.

        Focuses on high-level attributes like:
        - Product category (electronics, clothing, etc.)
        - Price range (budget, premium, etc.)
        - Brand specificity (if looking for specific brands)
        - Product type (physical, digital, services)
        """
        logger.info("🔍 Extracting store selection attributes from: %s", query)

        prompt = f"""You are a store selection specialist. Extract only the most relevant attributes for choosing stores:
        Query: "{query}"

        RULES:
        1. Return ONLY a valid JSON object
        2. All values must be strings
        3. Use ONLY these essential keys:
           - category: Main product category (electronics, clothing, books, etc.)
           - price_range: General range (budget, mid-range, premium)
           - brand_specific: Whether query targets specific brands (yes/no)
           - product_type: Type of good (physical, digital, service)
        4. Do not add any explanations
        5. Only include attributes that are clearly implied

        Example input: "cheap samsung phones under $200"
        Example output: {{
            "category": "electronics",
            "price_range": "budget",
            "brand_specific": "yes",
            "product_type": "physical"
        }}
        """

        try:
            ai_response = self.openai_service.generate_response(prompt)
            attributes = json.loads(ai_response)

            if not isinstance(attributes, dict):
                logger.error("❌ AI response was not a dictionary: %s", ai_response)
                return {"error": "Invalid AI response format"}
            return attributes

        except (OpenAIServiceError, json.JSONDecodeError) as e:
            logger.error("❌ Attribute extraction failed: %s", str(e))
            return {"error": str(e)}

    def refine_query_for_store(self, query: str, store: str) -> Dict[str, str]:
        """Refines the search query for a specific store's API format."""
        if not store.strip():
            logger.error("❌ Empty store name provided")
            return {}

        allowed_params = self.store_config.get_allowed_params(store)

        prompt = f"""You are a store API specialist. Convert this search query into API parameters:
        Query: "{query}"
        Store: {store}

        RULES:
        1. Return ONLY a valid JSON object
        2. Use EXACTLY these parameters: {allowed_params}
        3. All values must be strings
        4. Do not add any explanations or additional text
        5. Match parameter names exactly as provided

        Example input: "gaming laptop under $1000"
        Example output: {{"price.min": "800", "price.max": "1000", "categoryId": "abcat0502000"}}
        """

        try:
            ai_response = self.openai_service.generate_response(prompt)
            refined_query = json.loads(ai_response)

            validated_query = {k: str(v) for k, v in refined_query.items() if k in allowed_params}

            if not validated_query:
                logger.warning("⚠️ No valid parameters in refined query")
                return {}

            logger.info("✅ Refined query for %s: %s", store, validated_query)
            return validated_query

        except (OpenAIServiceError, json.JSONDecodeError) as e:
            logger.error("❌ Error refining query: %s", str(e))
            return {}
