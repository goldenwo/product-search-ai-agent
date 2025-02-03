from typing import Dict

from src.services.openai_service import OpenAIService
from src.utils import logger


class QueryParser:
    """
    AI-powered query parser that extracts structured product attributes
    from a user's natural language query.
    """

    def __init__(self):
        self.openai_service = OpenAIService()  # Load AI model

    def extract_product_attributes(self, query: str) -> Dict[str, str]:
        """
        Uses AI to extract structured product attributes from a search query.

        Args:
            query (str): The user's raw search query.

        Returns:
            Dict[str, str]: Extracted attributes (e.g., category, brand, budget).
        """
        prompt = f"""
        Extract key product attributes from the following search query:
        Query: "{query}"
        
        Return the attributes as a JSON dictionary with keys like 'category', 'brand', 
        'budget', 'size', 'color', etc. Example output:
        {{"category": "electronics", "brand": "Sony", "budget": "500"}}
        """
        logger.info(f"🔍 Processing user query: {query}")

        ai_response = self.openai_service.generate_response(prompt)

        # Convert AI response to dictionary
        try:
            attributes = eval(ai_response)  # Convert AI output to dict
            if isinstance(attributes, dict):
                logger.info(f"✅ Extracted attributes: {attributes}")
                return attributes
        except Exception as e:
            logger.error(f"❌ Error parsing AI response: {e}")

        return {}  # Default to empty dictionary if parsing fails
