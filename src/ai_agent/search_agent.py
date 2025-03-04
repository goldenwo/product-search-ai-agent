"""Search agent that coordinates the entire AI product search flow."""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from src.models.product import Product
from src.services.openai_service import OpenAIService
from src.services.product_enricher import ProductEnricher
from src.services.serp_service import SerpService
from src.utils import logger


class SearchAgent:
    """
    Coordinates the complete AI-powered product search workflow.

    This agent implements a streamlined search approach:
    1. Query SERP API to fetch initial product results
    2. Normalize the results into consistent format
    3. Enrich products with detailed specifications
    4. Rank products using LLM based on relevance to query and specs

    Attributes:
        openai_service: Service for accessing OpenAI APIs
        serp_service: Service for searching products through SERP APIs
        product_enricher: Service for retrieving detailed product specs
    """

    def __init__(self):
        """Initialize search agent components."""

        self.openai_service = OpenAIService()
        self.serp_service = SerpService()
        self.product_enricher = ProductEnricher()

    async def search(self, query: str, top_n: int = 10) -> List[Product]:
        """
        Perform complete product search given a user query.

        Args:
            query: User's search query string
            top_n: Number of top results to return

        Returns:
            List[Product]: Ranked list of products with metadata
        """
        if not query or not isinstance(query, str):
            logger.error("❌ Invalid search query provided")
            return []

        logger.info("🔍 Starting search for: %s", query)
        start_time = time.time()

        try:
            # 1. Fetch products from SERP API
            serp_results = await self.serp_service.search_products(query)
            if not serp_results:
                logger.warning("⚠️ No products found from SERP API")
                return []

            logger.info("✅ Retrieved %d products from SERP API", len(serp_results))

            # 2. Enrich the top SERP results with detailed specifications
            # Only enrich a subset of products to improve performance
            products_to_enrich = min(len(serp_results), 15)  # Limit to 15 products for enrichment
            enriched_products = await self._enrich_products(serp_results[:products_to_enrich])

            # 3. Rank products using LLM
            ranked_products = await self._rank_products(query, enriched_products)

            # 4. Return top results
            top_results = ranked_products[:top_n]

            # 5. Calculate and log total search time
            total_time = time.time() - start_time
            logger.info("✅ Search complete in %.2f seconds. Returning top %d products", total_time, len(top_results))

            return top_results

        except Exception as e:
            logger.error("❌ Error during search: %s", str(e))
            return []

    async def _enrich_products(self, products: List[Product]) -> List[Product]:
        """
        Enrich products with detailed specifications.

        Args:
            products: List of products to enrich

        Returns:
            List[Product]: Enriched products with specifications
        """
        logger.info("🔍 Enriching %d products with specifications", len(products))

        enriched_products = []
        product_enricher = ProductEnricher()

        # Process products in parallel for better performance
        async def enrich_single_product(product: Product) -> Product:
            try:
                enriched_product = await product_enricher.enrich_product(product)
                return enriched_product
            except Exception as e:
                logger.warning("⚠️ Error enriching product %s: %s", product.id, str(e))
                return product

        # Process up to 5 products at a time
        tasks = []
        for product in products:
            tasks.append(enrich_single_product(product))

        enriched_products = await asyncio.gather(*tasks)

        logger.info("✅ Successfully enriched %d products", len(enriched_products))
        return enriched_products

    async def _rank_products(self, query: str, products: List[Product]) -> List[Product]:
        """
        Rank products using LLM based on relevance to query and specifications.

        Args:
            query: Original search query
            products: List of enriched products with specifications

        Returns:
            List[Product]: Products with relevance scores, sorted by ranking
        """
        logger.info("🔍 Ranking %d products with LLM", len(products))

        if not products:
            return []

        # Extract intent and constraints from query
        intent_analysis = await self._analyze_query_intent(query)

        # Create a prompt for LLM to rank products
        prompt = self._create_ranking_prompt(query, products, intent_analysis)

        try:
            # Ask LLM to rank products
            ranking_response = self.openai_service.generate_response(prompt)

            # Parse ranking response into scores
            ranked_products, explanations = self._parse_ranking_response(ranking_response, products)

            # Sort by relevance score (descending)
            ranked_products.sort(key=lambda p: p.relevance_score or 0.0, reverse=True)

            # Add relevance explanation to top products
            for i, product in enumerate(ranked_products):
                if i < len(explanations):
                    product.relevance_explanation = explanations[i]

            logger.info("✅ Successfully ranked %d products", len(ranked_products))
            return ranked_products

        except Exception as e:
            logger.error("❌ Error ranking products: %s", str(e))
            # If ranking fails, return products with default scores
            for i, product in enumerate(products):
                product.relevance_score = 1.0 - (i / max(1, len(products)))
            return products

    async def _analyze_query_intent(self, query: str) -> Dict[str, Any]:
        """
        Analyze query to extract user intent and constraints.

        Args:
            query: User search query

        Returns:
            Dict[str, Any]: Intent analysis with product requirements
        """
        prompt = f"""Analyze this product search query to extract the user's intent and requirements:
        
Query: "{query}"

Return a JSON object with these fields:
1. primary_intent: Main goal (e.g., "find a laptop", "compare smartphones")
2. product_type: Primary product category
3. constraints: List of hard requirements (e.g., "budget under $500", "must be waterproof")
4. preferences: List of soft preferences (e.g., "prefer lightweight", "like high battery life")
5. keywords: List of important descriptive terms

Provide ONLY the JSON object without any additional text."""

        try:
            response = self.openai_service.generate_response(prompt)

            # Clean and parse the JSON response
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            intent_data = json.loads(cleaned_response)
            logger.info("✅ Successfully extracted search intent: %s", intent_data.get("primary_intent", "unknown"))
            return intent_data

        except Exception as e:
            logger.warning("⚠️ Failed to analyze query intent: %s", str(e))
            # Return basic intent analysis if parsing fails
            return {
                "primary_intent": "find products",
                "product_type": query.split()[-1] if query.split() else "product",
                "constraints": [],
                "preferences": [],
                "keywords": query.split(),
            }

    def _create_ranking_prompt(self, query: str, products: List[Product], intent_analysis: Dict[str, Any]) -> str:
        """
        Create a prompt for LLM to rank products based on relevance to query.

        Args:
            query: Original search query
            products: List of products to rank
            intent_analysis: Query intent and constraints

        Returns:
            str: Prompt for LLM
        """
        # Extract key information from intent analysis
        constraints = intent_analysis.get("constraints", [])
        preferences = intent_analysis.get("preferences", [])
        product_type = intent_analysis.get("product_type", "product")

        # Format products as a list in the prompt
        product_descriptions = []
        for i, product in enumerate(products):
            specs = product.specifications or {}
            description = (
                f"Product {i + 1}: {product.title}\n"
                f"  Price: {product.price}\n"
                f"  Brand: {product.brand}\n"
                f"  Store: {product.store}\n"
                f"  Rating: {product.rating} ({product.review_count} reviews)\n"
            )

            # Add key specifications
            specs_text = ""
            for key, value in specs.items():
                if key not in ["product_id", "name"]:  # Skip redundant fields
                    specs_text += f"  {key}: {value}\n"

            product_descriptions.append(description + specs_text)

        product_list = "\n\n".join(product_descriptions)

        # Format constraints and preferences
        constraints_text = "\n".join([f"- {c}" for c in constraints]) if constraints else "None specified"
        preferences_text = "\n".join([f"- {p}" for p in preferences]) if preferences else "None specified"

        # Create the ranking prompt
        prompt = f"""You are a product recommendation expert. Rank the following {product_type} products 
based on their relevance to this search query: "{query}"

USER REQUIREMENTS:
Hard Constraints:
{constraints_text}

Preferences:
{preferences_text}

PRODUCTS TO RANK:
{product_list}

For each product, determine:
1. A relevance score from 0.0 to 1.0, where 1.0 is perfectly relevant and 0.0 is completely irrelevant
2. A brief explanation of why this product matches or doesn't match the query (1-2 sentences)

Format your response as a JSON array of objects containing:
- product_index (1-based)
- relevance_score (0.0-1.0) 
- explanation (string)

Example:
[
  {{
    "product_index": 3,
    "relevance_score": 0.95,
    "explanation": "Excellent match for gaming needs with high-end GPU and meets budget requirement."
  }},
  {{
    "product_index": 1,
    "relevance_score": 0.82,
    "explanation": "Good processor but less ideal for gaming. Fits budget constraint."
  }}
]

Provide ONLY the JSON array, with no additional text.
"""
        return prompt

    def _parse_ranking_response(self, response: str, products: List[Product]) -> Tuple[List[Product], List[str]]:
        """
        Parse LLM ranking response and apply scores to products.

        Args:
            response: LLM response with ranking data
            products: Original list of products

        Returns:
            Tuple[List[Product], List[str]]:
                - Products with relevance scores added
                - List of explanations in rank order
        """
        import json

        try:
            # Clean the response string to ensure it contains only valid JSON
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            # Parse the JSON ranking
            rankings = json.loads(cleaned_response)

            # Apply scores to products
            ranked_products = products.copy()
            explanations = [""] * len(ranked_products)  # Initialize explanations list

            for rank_data in rankings:
                product_index = rank_data.get("product_index", 0) - 1  # Convert to 0-based
                if 0 <= product_index < len(ranked_products):
                    ranked_products[product_index].relevance_score = rank_data.get("relevance_score", 0.0)
                    explanations[product_index] = rank_data.get("explanation", "")

            # Sort explanations to match product order (by relevance score)
            product_indices = list(range(len(ranked_products)))
            product_indices.sort(key=lambda i: ranked_products[i].relevance_score or 0.0, reverse=True)
            sorted_explanations = [explanations[i] for i in product_indices]

            return ranked_products, sorted_explanations

        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
            logger.error("❌ Error parsing ranking response: %s", str(e))
            # Return products with default scores if parsing fails
            for i, product in enumerate(products):
                product.relevance_score = 1.0 - (i / max(1, len(products)))
            return products, [""] * len(products)

    async def get_product_details(self, product_id: str, url: str) -> Optional[Dict]:
        """
        Get detailed information about a specific product.

        Args:
            product_id: ID of the product to fetch
            url: URL of the product page

        Returns:
            Optional[Dict]: Detailed product information or None if not found
        """
        logger.info("🔍 Fetching detailed information for product: %s", product_id)

        try:
            # Use the product enricher to get detailed specifications
            specs = await self.product_enricher.get_product_specs(product_id=product_id, product_url=url)

            if specs:
                return {"id": product_id, "url": url, "specifications": specs}
            return None

        except Exception as e:
            logger.error("❌ Error fetching product details: %s", str(e))
            return None
