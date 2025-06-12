"""Search agent that coordinates the entire AI product search flow."""

import asyncio
import hashlib
import json
import re
import time
from typing import List

import redis

from src.models.product import Product
from src.services.openai_service import OpenAIService
from src.services.product_enricher import ProductEnricher
from src.services.redis_service import RedisService
from src.services.serp_service import SerpService
from src.utils import OpenAIServiceError, logger
from src.utils.config import (
    CACHE_ENRICHED_PRODUCT_TTL,
    CACHE_RANKING_TTL,
    ENRICHMENT_MAX_PARALLEL,
    OPENAI_CHAT_MODEL,
    SEARCH_ENRICHMENT_COUNT,
    SEARCH_INITIAL_FETCH_COUNT,
    SEARCH_RANKING_LIMIT,
)

# Cache key prefixes for better organization and debugging
CACHE_PREFIX_ENRICHED = "enriched_product"
CACHE_PREFIX_RANKING = "ranking"
CACHE_PREFIX_SEARCH = "search"  # Prefix for final search results cache in routes.py


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

    def __init__(
        self,
        redis_cache: RedisService,
        openai_service: OpenAIService,
        serp_service: SerpService,
        product_enricher: ProductEnricher,
        # Keep serp_provider optional if needed for direct instantiation elsewhere, but dependency injection is preferred
        # serp_provider: str = SerpProvider.SERPER
    ):
        """
        Initialize services needed for product search via dependency injection.

        Args:
            redis_cache: Shared Redis service instance
            openai_service: OpenAI service instance
            serp_service: SERP service instance
            product_enricher: Product enricher instance
        """
        # Assign injected services
        self.openai_service = openai_service
        self.serp_service = serp_service
        self.product_enricher = product_enricher
        self.redis_cache = redis_cache

        # Note: Previous internal instantiation removed in favor of DI

    async def search(self, query: str, top_n: int = 10) -> List[Product]:
        """
        Find top products for a search query with tiered processing.

        Args:
            query: User search query
            top_n: Number of products to return

        Returns:
            List[Product]: Ranked and enriched products

        This method uses a tiered approach to efficiently process results:
        1. Get initial products using configured fetch count.
        2. Selectively enrich top candidates based on configured enrichment count.
        3. Perform final ranking on relevant products using configured ranking limit.
        """
        start_time = time.time()
        logger.info("🔍 Starting search for query: '%s'", query)

        try:
            # Fetch initial products using configured count
            initial_fetch_count = min(SEARCH_INITIAL_FETCH_COUNT, 50)
            logger.info("Fetching initial %d products...", initial_fetch_count)
            products = await self.serp_service.search_products(query, num_results=initial_fetch_count)

            if not products:
                logger.warning("⚠️ No products found for query: %s", query)
                return []

            # --- Selective Enrichment Strategy ---
            enrichment_candidates_count = min(SEARCH_ENRICHMENT_COUNT, len(products))
            if enrichment_candidates_count > 0:
                logger.info("🎯 Selecting top %d candidates for enrichment.", enrichment_candidates_count)
                products_to_enrich = products[:enrichment_candidates_count]
                enriched_candidates = await self._enrich_products(products_to_enrich)
                enriched_map = {p.id: p for p in enriched_candidates}
            else:
                logger.info("📋 Skipping enrichment based on configuration (SEARCH_ENRICHMENT_COUNT=0).")
                enriched_map = {}

            # Create the final list for ranking: merge enriched + non-enriched products
            products_for_ranking = [enriched_map.get(p.id, p) for p in products]
            # Limit the number of products actually sent to the ranking AI based on config
            products_to_rank = products_for_ranking[: min(SEARCH_RANKING_LIMIT, len(products_for_ranking))]

            # Final ranking using AI
            logger.info("🏆 Performing final ranking on %d products (limit %d)", len(products_to_rank), SEARCH_RANKING_LIMIT)
            final_ranked_products = await self._rank_products(query, products_to_rank)

            # Trim to requested number
            result = final_ranked_products[:top_n]

            elapsed_time = time.time() - start_time
            logger.info("✅ Search completed in %.2f seconds, returning %d products", elapsed_time, len(result))

            return result
        except Exception as e:
            logger.error("❌ Unexpected error during search: %s", e)
            return []

    async def _enrich_products(self, products: List[Product], max_parallel: int = ENRICHMENT_MAX_PARALLEL) -> List[Product]:
        """
        Enrich products with specifications in controlled batches.

        Args:
            products: List of products to enrich
            max_parallel: Maximum number of products to process in parallel (defaults to config value)

        Returns:
            List[Product]: Enriched products with detailed specifications
        """
        if not products:
            return []

        # Use the effective max_parallel value from argument or config
        effective_max_parallel = max_parallel

        # Process enrichment in controlled batches
        logger.info("📋 Enriching %d products in batches of %d", len(products), effective_max_parallel)
        enriched_results = []
        batches = [products[i : i + effective_max_parallel] for i in range(0, len(products), effective_max_parallel)]

        for batch_idx, batch in enumerate(batches):
            logger.info("🔄 Processing enrichment batch %d/%d with %d products", batch_idx + 1, len(batches), len(batch))
            # Process batch with caching logic for each product
            enriched_batch_results = await asyncio.gather(*(self._enrich_with_cache(product) for product in batch))
            enriched_results.extend(enriched_batch_results)
            # Add a small delay between batches to be kind to target servers & APIs
            if len(batches) > 1 and batch_idx < len(batches) - 1:
                await asyncio.sleep(0.3)

        return enriched_results

    def _get_stable_enrichment_cache_key(self, product: Product) -> str:
        """Generates a stable cache key for enriched product data.

        Prioritizes stable identifiers (productId, sku, mpn) if available in specs.
        Falls back to a hash of the URL (excluding query params/fragments).
        Uses a potentially unstable key based on internal ID as a last resort.
        """
        specs = product.specifications or {}
        # Prioritize a unique ID from SERP/enrichment if available
        stable_id_part = specs.get("productId") or specs.get("product_id") or specs.get("sku") or specs.get("mpn")

        if stable_id_part:
            key = f"{CACHE_PREFIX_ENRICHED}_id:{stable_id_part}"
        elif product.url:
            url_str = str(product.url)
            url_parts = url_str.split("?")[0].split("#")[0]
            url_hash = hashlib.sha256(url_parts.encode()).hexdigest()
            key = f"{CACHE_PREFIX_ENRICHED}_urlhash:{url_hash}"
        else:
            # Last resort: use internal product ID (less stable if position changes)
            key = f"{CACHE_PREFIX_ENRICHED}_unstable:{product.id}"
            logger.warning("⚠️ Using potentially unstable cache key for product without URL or stable ID: %s", product.title)

        return key

    async def _enrich_with_cache(self, product: Product) -> Product:
        """
        Enrich a product with caching, using a stable key.
        Caches the full Product object as JSON.

        Args:
            product: Product to enrich

        Returns:
            Product: Enriched product with specifications
        """
        cache_key = self._get_stable_enrichment_cache_key(product)
        logger.debug("Using enrichment cache key: %s for product %s ('%s')", cache_key, product.id, product.title[:30])

        # Try to get from cache first
        cached_product_json = None
        try:
            cached_product_json = await self.redis_cache.get_cache(cache_key)
        except redis.RedisError as redis_err:
            logger.error("⚠️ Redis cache GET error for key '%s': %s. Will attempt enrichment.", cache_key, redis_err)
        except Exception as e:
            logger.error("❌ Unexpected error during enrichment cache GET for key '%s': %s. Will attempt enrichment.", cache_key, e)

        if cached_product_json:
            try:
                # Reconstruct the Product object from cached JSON
                enriched_product = Product.model_validate(cached_product_json)
                logger.info("✅ Cache hit for enriched product %s (Key: %s)", product.id, cache_key)
                return enriched_product
            except Exception as e:
                logger.warning("⚠️ Cache validation failed for product %s (Key: %s): %s. Re-enriching.", product.id, cache_key, e)
                # Proceed to enrichment if cache is invalid
        else:
            # Log miss only if no redis error occurred
            if cached_product_json is None:  # Check specifically for None, not just falsy
                logger.info("❌ Cache miss for enriched product %s (Key: %s)", product.id, cache_key)

        # If not in cache or cache invalid, perform enrichment
        try:
            logger.info("⏳ Enriching product %s from URL %s", product.id, product.url)
            start_enrich_time = time.time()
            enriched_product = await self.product_enricher.enrich_product(product)
            enrich_duration = time.time() - start_enrich_time
            # Log if enrichment actually added data
            if enriched_product.description != product.description or enriched_product.specifications != product.specifications:
                # Log details about what changed (e.g., description length, number of specs)
                desc_len_change = len(enriched_product.description or "") - len(product.description or "")
                spec_count_change = len(enriched_product.specifications or {}) - len(product.specifications or {})
                logger.info(
                    "✨ Enrichment added data for product %s (Desc chars: %+d, Specs: %+d) (%.2f seconds)",
                    product.id,
                    desc_len_change,
                    spec_count_change,
                    enrich_duration,
                )
            else:
                logger.info("☑️ Enrichment completed for product %s, but no new data added (%.2f seconds)", product.id, enrich_duration)

            # Cache the entire enriched product data as JSON
            try:
                await self.redis_cache.set_cache(
                    cache_key,
                    enriched_product.model_dump(mode="json"),
                    ttl=CACHE_ENRICHED_PRODUCT_TTL,
                )
                logger.info("💾 Cached enriched data for product %s (Key: %s, TTL: %ds)", product.id, cache_key, CACHE_ENRICHED_PRODUCT_TTL)
            except redis.RedisError as redis_err:
                logger.error("⚠️ Redis cache SET error for enrichment key '%s': %s. Enrichment completed but not cached.", cache_key, redis_err)
            except Exception as e:
                logger.error("❌ Unexpected error during enrichment cache SET for key '%s': %s", cache_key, e)
            return enriched_product

        except Exception as e:
            logger.error("❌ Error during enrichment process for product %s (Key: %s): %s", product.id, cache_key, e)
            return product  # Return original product if enrichment fails

    async def _rank_products(self, query: str, products: List[Product]) -> List[Product]:
        """
        Rank products by relevance to query using LLM.

        Args:
            query: User search query
            products: List of products to rank (potentially mixed enrichment levels)

        Returns:
            List[Product]: Products sorted by relevance score
        """
        if not products:
            return []

        # Optimization: Skip expensive AI ranking for trivial cases
        if len(products) <= 1:
            if products:
                products[0].relevance_score = 1.0  # Assign default score
                products[0].relevance_explanation = "Top result based on initial fetch."
            return products

        # Check cache for existing ranking results
        # Generate cache key based on query and a hash of stable product identifiers
        stable_product_ids = sorted([self._get_stable_enrichment_cache_key(p) for p in products])
        product_ids_key_part = "-".join(stable_product_ids)
        product_set_hash = hashlib.sha256(product_ids_key_part.encode()).hexdigest()[:16]  # Short hash
        rank_cache_key = f"{CACHE_PREFIX_RANKING}:{query.lower()}:{product_set_hash}"
        logger.debug("Using ranking cache key: %s", rank_cache_key)

        cached_ranking = None
        try:
            cached_ranking = await self.redis_cache.get_cache(rank_cache_key)
        except redis.RedisError as redis_err:
            logger.error("⚠️ Redis cache GET error for ranking key '%s': %s. Will attempt ranking.", rank_cache_key, redis_err)
        except Exception as e:
            logger.error("❌ Unexpected error during ranking cache GET for key '%s': %s. Will attempt ranking.", rank_cache_key, e)

        if cached_ranking:
            logger.info("✅ Cache hit for ranking query: '%s' (Key: %s)", query, rank_cache_key)
            ranked_products = products.copy()  # Work on a copy

            # Apply cached relevance scores and explanations
            product_map_for_cache = {self._get_stable_enrichment_cache_key(p): p for p in ranked_products}
            found_in_cache_count = 0

            if isinstance(cached_ranking, dict):
                for cache_id_key, rank_data in cached_ranking.items():
                    if cache_id_key in product_map_for_cache:
                        product = product_map_for_cache[cache_id_key]
                        try:
                            product.relevance_score = float(rank_data.get("score")) if rank_data.get("score") is not None else None
                            product.relevance_explanation = rank_data.get("explanation")
                            if "category_scores" in rank_data:
                                self._apply_category_scores(product, rank_data["category_scores"], rank_data.get("category_definitions", {}))
                            found_in_cache_count += 1
                        except (ValueError, TypeError) as parse_err:
                            logger.warning("⚠️ Error applying cached rank data for %s: %s", cache_id_key, parse_err)
                            product.relevance_score = None
                    else:
                        logger.warning("⚠️ Product with cache key %s not found in current product set for ranking.", cache_id_key)
            else:
                logger.error("❌ Invalid format for cached ranking data (expected dict): %s. Skipping cache application.", type(cached_ranking))

            if found_in_cache_count > 0:
                logger.info("Applied cached ranking data to %d products.", found_in_cache_count)
            else:
                logger.warning("⚠️ Ranking cache hit, but failed to apply data to any products.")
                # Proceed as cache miss if application failed completely

            # Sort by relevance score (handle potential None scores)
            ranked_products.sort(key=lambda p: p.relevance_score if p.relevance_score is not None else -1.0, reverse=True)
            return ranked_products
        else:
            logger.info("❌ Cache miss for ranking query: '%s' (Key: %s)", query, rank_cache_key)

        # Prepare prompt for AI ranking
        prompt = self._create_efficient_ranking_prompt(query, products)
        logger.debug("Ranking prompt length: %d characters", len(prompt))

        try:
            # Get ranking from LLM
            logger.info("⏳ Requesting ranking from AI model: %s", OPENAI_CHAT_MODEL)
            start_rank_time = time.time()

            # Get the full response object from the service
            response_obj = await self.openai_service.generate_response(prompt, model=OPENAI_CHAT_MODEL, max_tokens=3000)
            rank_duration = time.time() - start_rank_time

            # Extract content and log usage
            response_content = response_obj.choices[0].message.content if response_obj.choices and response_obj.choices[0].message.content else None
            if response_obj.usage:
                logger.info(
                    "📊 OpenAI Ranking Usage - Prompt: %d, Completion: %d, Total: %d tokens",
                    response_obj.usage.prompt_tokens,
                    response_obj.usage.completion_tokens,
                    response_obj.usage.total_tokens,
                )

            if not response_content:
                logger.error("❌ AI ranking response content is empty.")
                return self._create_emergency_fallback(products, "Ranking system error: Empty response")

            logger.info("⏱️ AI ranking completed in %.2f seconds", rank_duration)

            # Parse the response content (string)
            ranked_products = self._parse_ranking_response(response_content, products)

            # Cache the ranking results
            # Store results mapped by stable product key for reliable retrieval
            ranking_data_to_cache = {}  # Initialize the dictionary
            for p in ranked_products:
                if p.relevance_score is not None:
                    stable_key = self._get_stable_enrichment_cache_key(p)
                    ranking_data_to_cache[stable_key] = {
                        "score": p.relevance_score,
                        "explanation": p.relevance_explanation,
                        "category_scores": getattr(p, "raw_category_scores", {}),
                        "category_definitions": p.specifications.get("CategoryDefinitions", {}),
                    }

            if ranking_data_to_cache:
                try:
                    await self.redis_cache.set_cache(rank_cache_key, ranking_data_to_cache, ttl=CACHE_RANKING_TTL)
                    logger.info("💾 Cached ranking data (Key: %s, TTL: %ds)", rank_cache_key, CACHE_RANKING_TTL)
                except redis.RedisError as redis_err:  # Catch specific Redis errors
                    logger.error("⚠️ Redis cache SET error for ranking key '%s': %s. Ranking completed but not cached.", rank_cache_key, redis_err)
                except Exception as e:
                    logger.error("❌ Unexpected error during ranking cache SET for key '%s': %s", rank_cache_key, e)
            else:
                logger.warning("⚠️ No ranking data with scores generated, nothing to cache.")

            return ranked_products
        except OpenAIServiceError as e:
            logger.error("❌ AI Service error during ranking: %s. Using fallback.", e)
            return self._create_emergency_fallback(products, "Ranking system error")
        except Exception as e:
            logger.error("❌ Unexpected error ranking products: %s. Using fallback.", e)
            return self._create_emergency_fallback(products, "Ranking system unavailable")

    def _create_efficient_ranking_prompt(self, query: str, products: List[Product]) -> str:
        """
        Create a prompt for ranking products that efficiently uses token space.
        This uses a two-step process:
        1. Identify product-specific evaluation categories based on the product set
        2. Rank products using those categories

        Args:
            query: Original search query
            products: Products to rank (may have varying levels of detail)

        Returns:
            str: Optimized prompt for AI ranking
        """
        if not products:
            return ""

        # Add context about the number of products and the two-step process
        prompt = f"""You are a product ranking specialist helping rank {len(products)} products for the search query: "{query}"

YOUR TASK: You will perform a two-step analysis:
1. FIRST: Identify 4-6 evaluation categories specific to this product type and search context
2. SECOND: Rank each product using these categories

STEP 1 - IDENTIFY RELEVANT EVALUATION CATEGORIES:
Analyze the product set and dynamically identify 4-6 evaluation categories that are:
- Specific and appropriate to this exact product type (DO NOT use generic categories)
- Highly relevant to the search query intent: "{query}"
- Measurable and comparable across the specific products in this result set
- Reflective of what customers value when shopping for this specific product type
- Informed by product specifications, descriptions, and other product details

STEP 2 - RANK PRODUCTS:
Use these categories to perform a comprehensive evaluation of each product, considering:
- How well each product performs in each category (score out of 10)
- Overall relevance to the search query and user intent
- Price-value ratio considering the product's specifications and features
- Brand reputation and customer sentiment where available
- Any unique features or selling points that differentiate products
- **IMPORTANT: Some products may have limited details (missing description or specs).
Base your ranking primarily on available information and relevance to the query. 
Do not heavily penalize products solely for missing data if they seem relevant otherwise.**

FORMAT: Provide your analysis as JSON with this structure:
```json
{{
  "evaluation_categories": [
    {{
      "name": "Category Name",
      "description": "Brief description of what this category measures and why it matters for this product type"
    }},
    ...
  ],
  "rankings": [
    {{
      "product": 1,
      "score": 0.95,
      "category_scores": {{
        "Category Name": 9,
        ...
      }},
      "explanation": "Detailed explanation of ranking decision that references specific product attributes"
    }},
    ...
  ]
}}
```

PRODUCTS:
"""

        # Add product details, limiting description and specs for token efficiency
        for i, product in enumerate(products, 1):
            # Create a view of product details relevant for ranking
            product_details = [
                f"PRODUCT #{i}:",
                f"Title: {product.title}",
                f"Store: {product.store or 'Unknown'}",
                f"Brand: {product.brand or 'Unknown'}",
                f"Price: {product.format_price()}",
                f"Rating: {product.rating or 'No ratings'} ({product.review_count or 0} reviews)",
                f"Category: {product.category or 'Uncategorized'}",
            ]

            # Include a short snippet of the description if available
            if product.description:
                desc_limit = 80  # Limit description length for ranking prompt
                short_desc = product.description[:desc_limit] + "..." if len(product.description) > desc_limit else product.description
                product_details.append(f"Description Snippet: {short_desc}")
            else:
                product_details.append("Description: Not Available")

            # Include only a few key specifications if available
            if product.specifications:
                # Filter out internal/score/ID specs before display
                display_specs = {
                    k: v
                    for k, v in product.specifications.items()
                    if not k.startswith(("Score:", "NormalizedScore:", "RawCategoryScores", "CategoryDefinitions"))
                    and k not in ["productId", "serpId", "itemId", "sku", "mpn", "gtin", "condition"]
                }

                if display_specs:
                    spec_limit = 4  # Limit number of specs shown in prompt
                    important_specs = list(display_specs.items())[:spec_limit]
                    specs_text = "; ".join(f"{k}: {v}" for k, v in important_specs)
                    product_details.append(f"Key Specifications: {specs_text}")
                else:
                    product_details.append("Specifications: None Available")
            else:
                product_details.append("Specifications: Not Available")

            # Add shipping info if available
            if product.shipping:
                product_details.append(f"Shipping: {product.shipping}")

            prompt += "\n" + "\n".join(product_details) + "\n"

        # Add final instructions for balanced evaluation and JSON format
        prompt += """
 IMPORTANT GUIDELINES:
 - First analyze what categories are most appropriate for THIS SPECIFIC product type - don't use generic categories
 - Create categories that reflect how customers would evaluate these exact products in the real world
 - DO NOT use predefined categories - generate them based on the specific product set and search context
 - Score products from 0-10 in each category (10 is perfect)
 - Calculate an overall score for each product from 0.0-1.0 based on category scores
 - Provide detailed explanations that reference specific product attributes and features **available**
 - The search query intent should be the primary consideration for relevance scoring
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
            List[Product]: Products with default scores sorted by position
        """
        logger.warning("⚠️ Using emergency alphabetical ordering fallback")
        fallback_products = products.copy()

        for product in fallback_products:
            product.relevance_score = 0.5  # Neutral score
            product.relevance_explanation = message

        # Sort by original position (lower is better), putting None positions last
        # Use a large number for None positions to ensure they are sorted to the end.
        fallback_products.sort(key=lambda p: p.position if p.position is not None else float("inf"))
        return fallback_products

    def _parse_ranking_response(self, response_content: str, products: List[Product]) -> List[Product]:
        """
        Parse LLM ranking response string and update product scores.

        Args:
            response_content: LLM response content string (JSON expected)
            products: Original product list

        Returns:
            List[Product]: Ranked products with relevance scores and explanations

        Raises:
            JSONDecodeError: If response can't be parsed as JSON
            KeyError: If expected keys are missing from response
        """
        ranked_products = products.copy()  # Work on a copy

        # Extract JSON from response string more robustly
        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", response_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Fallback: Try finding the first '{' and last '}'
                start = response_content.find("{")
                end = response_content.rfind("}")
                if start != -1 and end != -1:
                    json_str = response_content[start : end + 1]
                else:
                    logger.error("❌ Could not extract JSON block from ranking response.")
                    raise json.JSONDecodeError("No JSON object found", response_content, 0)

            data = json.loads(json_str)
            if not isinstance(data, dict):
                logger.error("❌ Parsed ranking JSON is not a dictionary.")
                raise ValueError("Parsed JSON is not a dictionary")

        except json.JSONDecodeError as e:
            logger.error("❌ Failed to decode JSON from ranking response: %s\nResponse: %s", e, response_content[:500])
            raise  # Re-raise to be caught by caller, triggering fallback

        # Extract evaluation categories and definitions
        categories = data.get("evaluation_categories", [])
        if isinstance(categories, list):
            # Filter out None names before joining
            category_names = [name for cat in categories if isinstance(cat, dict) and (name := cat.get("name"))]
            if category_names:
                logger.info("📊 AI evaluation categories used: %s", ", ".join(category_names))
            category_definitions = {cat.get("name"): cat.get("description") for cat in categories if isinstance(cat, dict) and cat.get("name")}
        else:
            logger.warning("⚠️ Evaluation categories format unexpected or missing in ranking response.")
            category_definitions = {}

        # Extract rankings
        rankings = data.get("rankings", [])
        if not isinstance(rankings, list) or not rankings:
            logger.error("❌ No rankings list found or empty in response")
            # Proceeding, but some products might not get scores
            pass

        # Create a map for quick product access by original index (1-based from prompt)
        product_map = {i + 1: p for i, p in enumerate(ranked_products)}
        ranked_count = 0

        # Apply scores and explanations
        for rank_data in rankings:
            if not isinstance(rank_data, dict):
                logger.warning("⚠️ Skipping invalid rank data item: %s", str(rank_data))
                continue

            product_idx = rank_data.get("product")  # Corresponds to PRODUCT #i in prompt
            # Check if product_idx is a valid integer index
            if isinstance(product_idx, int) and product_idx in product_map:
                product = product_map[product_idx]
                try:
                    score = rank_data.get("score")
                    product.relevance_score = float(score) if score is not None else None
                    product.relevance_explanation = str(rank_data.get("explanation", "")).strip()

                    # Process and store category scores
                    category_scores_raw = rank_data.get("category_scores", {})
                    if isinstance(category_scores_raw, dict):
                        self._apply_category_scores(product, category_scores_raw, category_definitions)

                    ranked_count += 1
                except (ValueError, TypeError) as e:
                    logger.warning("⚠️ Error processing rank data for product #%s: %s. Data: %s", product_idx, e, rank_data)
                    product.relevance_score = None  # Ensure score is None if parsing fails
                    product.relevance_explanation = "Error processing ranking data."
            else:
                logger.warning("⚠️ Product index '%s' from ranking not found in product map or invalid.", product_idx)

        # Sort by relevance score (descending), putting None scores last
        ranked_products.sort(key=lambda p: p.relevance_score if p.relevance_score is not None else -1.0, reverse=True)

        logger.info("✅ Successfully parsed ranking for %d products.", ranked_count)
        return ranked_products

    def _apply_category_scores(self, product: Product, category_scores_raw: dict, category_definitions: dict):
        """Helper to apply category scores (0-10 scale) and definitions to a product's specifications.

        Normalizes scores to 0.0-1.0 and stores raw/formatted scores.
        """
        # Stores scores directly within the product's specifications dictionary
        if product.specifications is None:
            product.specifications = {}
        raw_scores_dict = {}  # Temporary dict to hold raw scores before adding to specs

        for category, score_val in category_scores_raw.items():
            try:
                score_num = float(score_val)  # Expecting 0-10 scale from prompt
                if 0 <= score_num <= 10:
                    normalized_score = score_num / 10.0
                    # Store formatted scores in main specs
                    product.specifications[f"Score: {category}"] = f"{score_num:.1f}/10"
                    product.specifications[f"NormalizedScore: {category}"] = f"{normalized_score:.2f}"
                    # Store raw score in the temporary dict for later inclusion
                    raw_scores_dict[category] = score_num
                else:
                    logger.warning("⚠️ Category score '%s' for '%s' out of range (0-10)", score_val, category)
            except (ValueError, TypeError):
                logger.warning("⚠️ Could not parse category score '%s' for '%s' as number.", score_val, category)

        # Store the dictionary of raw scores within specifications under a specific key
        if raw_scores_dict:
            product.specifications["RawCategoryScores"] = raw_scores_dict

        # Store category definitions if available
        if category_definitions:
            product.specifications["CategoryDefinitions"] = category_definitions
