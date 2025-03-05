"""Search agent that coordinates the entire AI product search flow."""

import asyncio
import json
import re
import time
from typing import List, Optional

from src.models.product import Product
from src.services.openai_service import OpenAIService
from src.services.product_enricher import ProductEnricher
from src.services.redis_service import RedisService
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
        redis_cache: Service for caching results
    """

    def __init__(self, redis_cache: Optional[RedisService] = None):
        """
        Initialize services needed for product search.

        Args:
            redis_cache: Optional shared Redis service instance
        """
        self.openai_service = OpenAIService()
        self.serp_service = SerpService()
        self.product_enricher = ProductEnricher()
        # Use provided Redis service or create a new one if not provided
        self.redis_cache = redis_cache or RedisService()

    async def search(self, query: str, top_n: int = 10) -> List[Product]:
        """
        Find top products for a search query with tiered processing.

        Args:
            query: User search query
            top_n: Number of products to return

        Returns:
            List[Product]: Ranked and enriched products

        This method uses a tiered approach to efficiently process results:
        1. Get initial products (2x requested amount)
        2. Perform basic ranking on all products
        3. Deeply enrich only the top candidates
        4. Final re-ranking with enriched data
        """
        start_time = time.time()
        logger.info("🔍 Starting search for query: %s", query)

        # Get initial products (2x requested amount for better filtering)
        initial_fetch_count = min(top_n * 2, 20)  # Cap at 20 to avoid excessive API usage
        # Use correct parameter name (num instead of limit)
        products = await self.serp_service.search_products(query, num_results=initial_fetch_count)

        if not products:
            logger.warning("⚠️ No products found for query: %s", query)
            return []

        # First-pass ranking based on initial data
        logger.info("🏆 Performing initial ranking on %d products", len(products))
        ranked_products = await self._rank_products(query, products)

        # Select top candidates for enrichment (1.5x requested to allow for filtering)
        enrichment_candidates = ranked_products[: min(top_n * 3 // 2, 15)]

        # Selectively enrich top products
        logger.info("🔍 Enriching top %d products with detailed specifications", len(enrichment_candidates))
        enriched_products = await self._enrich_products(enrichment_candidates)

        # Final ranking with enriched data
        logger.info("🏆 Performing final ranking with enriched data")
        final_ranked_products = await self._rank_products(query, enriched_products)

        # Trim to requested number
        result = final_ranked_products[:top_n]

        elapsed_time = time.time() - start_time
        logger.info("✅ Search completed in %.2f seconds, returning %d products", elapsed_time, len(result))

        return result

    async def _enrich_products(self, products: List[Product], max_parallel: int = 3) -> List[Product]:
        """
        Enrich products with specifications in controlled batches.

        Args:
            products: List of products to enrich
            max_parallel: Maximum number of products to process in parallel

        Returns:
            List[Product]: Enriched products with detailed specifications
        """
        if not products:
            return []

        # Filter out products that already have rich data
        enrichment_candidates = []
        for product in products:
            # Skip products that already have rich data
            if product.description and len(product.description) > 100 and product.has_specifications() and len(product.specifications) > 5:
                logger.info("📋 Product %s already has rich data, skipping enrichment", product.id)
                continue

            enrichment_candidates.append(product)

        if not enrichment_candidates:
            return products

        # Process in batches to control API usage
        logger.info("📋 Enriching %d products in batches of %d", len(enrichment_candidates), max_parallel)
        enriched_products = []
        batches = [enrichment_candidates[i : i + max_parallel] for i in range(0, len(enrichment_candidates), max_parallel)]

        for batch_idx, batch in enumerate(batches):
            logger.info("📋 Processing batch %d/%d with %d products", batch_idx + 1, len(batches), len(batch))

            # Process batch with caching
            enriched_batch = await asyncio.gather(*(self._enrich_with_cache(product) for product in batch))
            enriched_products.extend(enriched_batch)

            # Add a small delay between batches to prevent rate limiting
            if batch_idx < len(batches) - 1:
                await asyncio.sleep(0.5)

        # Update original products list with enriched data
        enriched_map = {p.id: p for p in enriched_products}
        result = [enriched_map.get(p.id, p) for p in products]

        return result

    async def _enrich_with_cache(self, product: Product) -> Product:
        """
        Enrich a product with caching to avoid redundant API calls.

        Args:
            product: Product to enrich

        Returns:
            Product: Enriched product with specifications
        """
        # Create a cache key based on product ID and URL
        cache_key = f"enriched_product:{product.id}"

        # Try to get from cache first
        cached_specs = await self.redis_cache.get_cache(cache_key)
        if cached_specs:
            logger.info("📋 Using cached specifications for product %s", product.id)
            # Update product with cached specs
            for key, value in cached_specs.items():
                if key not in product.specifications:
                    product.specifications[key] = value
            return product

        # If not in cache, perform enrichment
        try:
            logger.info("📋 Enriching product %s from URL %s", product.id, product.url)
            enriched_product = await self.product_enricher.enrich_product(product)

            # Cache the specifications (1 day TTL)
            if enriched_product.specifications:
                await self.redis_cache.set_cache(
                    cache_key,
                    enriched_product.specifications,
                    ttl=86400,  # Cache for 24 hours
                )

            return enriched_product
        except Exception as e:
            logger.error("❌ Error enriching product %s: %s", product.id, str(e))
            return product  # Return original product if enrichment fails

    async def _rank_products(self, query: str, products: List[Product]) -> List[Product]:
        """
        Rank products by relevance to query using LLM.

        Args:
            query: User search query
            products: List of products to rank

        Returns:
            List[Product]: Products sorted by relevance score
        """
        if not products:
            return []

        # For very small result sets, skip expensive ranking
        if len(products) <= 3:
            # Just assign simple scores
            for i, product in enumerate(products):
                product.relevance_score = 1.0 - (i * 0.1)
            return products

        # Check if we have cached ranking for this query and product set
        product_ids = "-".join(sorted([p.id for p in products]))
        rank_cache_key = f"ranking:{query.lower()}:{product_ids}"

        cached_ranking = await self.redis_cache.get_cache(rank_cache_key)
        if cached_ranking:
            logger.info("🏆 Using cached ranking for query: %s", query)
            ranked_products = products.copy()

            # Apply cached relevance scores
            for product in ranked_products:
                if product.id in cached_ranking:
                    product.relevance_score = cached_ranking[product.id]["score"]
                    product.relevance_explanation = cached_ranking[product.id].get("explanation", None)

            # Sort by relevance score
            ranked_products.sort(key=lambda p: p.relevance_score or 0.0, reverse=True)
            return ranked_products

        # Create an efficient prompt for ranking
        prompt = self._create_efficient_ranking_prompt(query, products)

        try:
            # Get ranking from LLM
            response = self.openai_service.generate_response(prompt)

            # Parse the response
            ranked_products = self._parse_ranking_response(response, products)

            # Cache the ranking results (3 hours TTL)
            ranking_data = {
                p.id: {"score": p.relevance_score, "explanation": p.relevance_explanation} for p in ranked_products if p.relevance_score is not None
            }

            await self.redis_cache.set_cache(rank_cache_key, ranking_data, ttl=10800)

            return ranked_products
        except Exception as e:
            logger.error("❌ Error ranking products: %s", str(e))
            # Use the shared emergency fallback method
            return self._create_emergency_fallback(products, "Ranking system unavailable")

    def _create_efficient_ranking_prompt(self, query: str, products: List[Product]) -> str:
        """
        Create a prompt for ranking products that efficiently uses token space.
        This uses a two-step process:
        1. Identify product-specific evaluation categories
        2. Rank products using those categories

        Args:
            query: Original search query
            products: Products to rank

        Returns:
            str: Optimized prompt for AI ranking
        """
        if not products:
            return ""

        # Add context about the number of products and the two-step process
        prompt = f"""You are a product ranking specialist helping rank {len(products)} products for the search query: "{query}"

YOUR TASK: You will perform a two-step analysis:
1. FIRST: Identify 4-6 evaluation categories specific to this product type
2. SECOND: Rank each product using these categories

STEP 1 - IDENTIFY RELEVANT EVALUATION CATEGORIES:
Analyze the product set and identify 4-6 evaluation categories that are:
- Specific to this product type (e.g., for clothing: fit, material quality, style; for electronics: performance, battery life, build quality)
- Relevant to the search query: "{query}"
- Measurable and comparable across products
- Reflective of what customers value for this product type

STEP 2 - RANK PRODUCTS:
Use these categories to perform a comprehensive evaluation of each product, considering:
- How well each product performs in each category
- Overall relevance to the search query
- Price-value ratio
- Brand reputation and customer sentiment

FORMAT: Provide your analysis as JSON with this structure:
```json
{{
  "evaluation_categories": [
    {{
      "name": "Category Name",
      "description": "Brief description of what this category measures"
    }},
    ...
  ],
  "rankings": [
    {{
      "product": 1,
      "score": 0.95,
      "category_scores": {{
        "Category Name": 0.9,
        ...
      }},
      "explanation": "Brief explanation of ranking decision"
    }},
    ...
  ]
}}
```

PRODUCTS:
"""

        # Add comprehensive product information including brand, specs, and more details
        for i, product in enumerate(products, 1):
            # Create a comprehensive product view with all details
            product_details = [
                f"PRODUCT #{i}:",
                f"Title: {product.title}",
                f"Brand: {product.brand or 'Unknown'}",
                f"Price: {product.format_price()}",
                f"Rating: {product.rating or 'No ratings'} ({product.review_count or 0} reviews)",
                f"Category: {product.category or 'Uncategorized'}",
            ]

            # Add short description if available
            if product.description:
                # Limit description length to save tokens
                short_desc = product.description[:150] + "..." if len(product.description) > 150 else product.description
                product_details.append(f"Description: {short_desc}")

            # Add key specifications if available
            if product.specifications:
                # Select most important specs (up to 5)
                important_specs = list(product.specifications.items())[:5]
                specs_text = "; ".join(f"{k}: {v}" for k, v in important_specs)
                if len(important_specs) < len(product.specifications):
                    specs_text += f"; ... and {len(product.specifications) - len(important_specs)} more specs"
                product_details.append(f"Specifications: {specs_text}")

            # Add shipping info if available
            if product.shipping:
                product_details.append(f"Shipping: {product.shipping}")

            prompt += "\n" + "\n".join(product_details) + "\n"

        # Add final instructions for balanced evaluation
        prompt += """
IMPORTANT:
- First analyze what categories are most important for this specific product type
- Create categories that are relevant to how customers would evaluate these products
- Score products from 0.0 to 1.0 in each category (1.0 is perfect)
- Calculate an overall score for each product based on category scores
- Provide brief explanations that reference the category scores
- Consider the search query intent as the primary ranking factor
- Return ONLY valid JSON following the exact format specified
"""
        return prompt

    def _create_emergency_fallback(self, products: List[Product], message: str) -> List[Product]:
        """
        Create a fallback sorted product list when AI ranking fails.

        Args:
            products: List of products to sort
            message: Explanation message to add to products

        Returns:
            List[Product]: Products with default scores sorted alphabetically
        """
        logger.warning("⚠️ Using emergency alphabetical ordering fallback")
        fallback_products = products.copy()

        for product in fallback_products:
            product.relevance_score = 0.5  # Neutral score
            product.relevance_explanation = message

        # Sort alphabetically as ultimate fallback
        fallback_products.sort(key=lambda p: p.title)
        return fallback_products

    def _parse_ranking_response(self, response: str, products: List[Product]) -> List[Product]:
        """
        Parse LLM ranking response and update product scores.

        Args:
            response: LLM response with rankings
            products: Original product list

        Returns:
            List[Product]: Ranked products with relevance scores and explanations

        Raises:
            JSONDecodeError: If response can't be parsed as JSON
            KeyError: If expected keys are missing from response
        """
        ranked_products = products.copy()

        # Extract JSON from response
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            response = json_match.group(1)
        else:
            # Try to extract just the JSON object
            json_match = re.search(r"(\{.*\})", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            else:
                # If we can't extract JSON, raise an error that will be caught by the caller
                logger.error("❌ Failed to extract JSON from response")
                raise json.JSONDecodeError("Unable to extract JSON from response", response, 0)

        data = json.loads(response)

        # Extract evaluation categories (new feature)
        categories = data.get("evaluation_categories", [])
        category_names = [cat.get("name") for cat in categories]
        logger.info("🔍 Using evaluation categories: %s", ", ".join(category_names))

        # Extract rankings
        rankings = data.get("rankings", [])
        if not rankings:
            logger.error("❌ No rankings found in response")
            raise KeyError("No rankings found in response data")

        # Create a map for quick product access
        product_map = {i + 1: p for i, p in enumerate(ranked_products)}

        # Apply scores and explanations
        for rank_data in rankings:
            product_idx = rank_data.get("product")
            if product_idx in product_map:
                product = product_map[product_idx]
                product.relevance_score = rank_data.get("score")

                # Create enhanced explanation that includes category scores
                category_scores = rank_data.get("category_scores", {})
                explanation = rank_data.get("explanation", "")

                if category_scores:
                    # Store category scores in specifications
                    for category, score in category_scores.items():
                        product.specifications[f"Score: {category}"] = score

                product.relevance_explanation = explanation

        # Sort by relevance score (descending)
        ranked_products.sort(key=lambda p: p.relevance_score or 0.0, reverse=True)

        # Add relevance explanation to top products
        logger.info("🏆 Successfully ranked %d products", len(ranked_products))
        return ranked_products
