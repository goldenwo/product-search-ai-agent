"""Natural language query parser for product search refinement."""

import json
from typing import Dict, Optional

from src.services.openai_service import OpenAIService
from src.utils import OpenAIServiceError, logger
from src.utils.store_config import StoreConfig


class QueryParser:
    """
    Parses and refines natural language search queries.

    Handles:
    - Attribute extraction
    - Store-specific query formatting
    - Price range parsing
    - Category detection
    """

    def __init__(self):
        self.openai_service = OpenAIService()  # Load AI model
        self.store_config = StoreConfig()

    def extract_product_attributes(self, query: str) -> Dict[str, str]:
        """
        Extract structured attributes from natural language query.

        Args:
            query: Raw search query from user

        Returns:
            Dict[str, str]: Extracted attributes (category, price_range, brand, etc.)

        Example:
            "cheap gaming laptop under $1000" ->
            {
                "category": "laptop",
                "use_case": "gaming",
                "price_max": "1000",
                "price_qualifier": "under"
            }
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

    def refine_query_for_store(self, query: str, store_name: str) -> Optional[Dict[str, str]]:
        """
        Adapt query parameters for specific store APIs.

        Args:
            query: Original search query
            store_name: Target store name

        Returns:
            Optional[Dict[str, str]]: Store-specific query parameters
            None if store is not supported

        Example:
            ("gaming laptop", "amazon") ->
            {
                "keywords": "gaming laptop",
                "department": "computers",
                "sort": "rating"
            }
        """
        if not store_name.strip():
            logger.error("❌ Empty store name provided")
            return None

        allowed_params = self.store_config.get_allowed_params(store_name)

        prompt = f"""You are a store API specialist. Convert this search query into API parameters:
        Query: "{query}"
        Store: {store_name}

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
                return None

            logger.info("✅ Refined query for %s: %s", store_name, validated_query)
            return validated_query

        except (OpenAIServiceError, json.JSONDecodeError) as e:
            logger.error("❌ Error refining query: %s", str(e))
            return None
