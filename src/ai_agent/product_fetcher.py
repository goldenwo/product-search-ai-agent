"""Product fetcher service that coordinates the AI-powered product search workflow."""

import asyncio
from decimal import Decimal
from typing import Dict, List

import aiohttp
import numpy as np
from requests.exceptions import RequestException, Timeout

from src.ai_agent.query_parser import QueryParser
from src.ai_agent.store_selector import StoreSelector
from src.models.product import Product  # Import the shared Product model
from src.services.faiss_service import FAISSService
from src.services.openai_service import OpenAIService
from src.services.redis_service import RedisService
from src.utils import FAISS_VECTOR_DIMENSION, FAISSIndexError, OpenAIServiceError, logger
from src.utils.store_config import StoreConfig


class ProductFetcher:
    """
    Fetches and ranks products following the AI-powered search flow.
    """

    def __init__(self):
        self.query_parser = QueryParser()
        self.store_selector = StoreSelector()
        self.faiss_service = FAISSService()
        self.openai_service = OpenAIService()
        self.store_config = StoreConfig()
        self.redis_cache = RedisService()

    async def fetch_from_store(self, store_name: str, refined_query: Dict[str, str]) -> List[Product]:
        """Fetch products from store API with refined query."""
        store_name = store_name.lower()
        cache_key = f"store:{store_name}:{hash(frozenset(refined_query.items()))}"

        # Check cache first
        cached_results = self.redis_cache.get_cache(cache_key)
        if cached_results:
            logger.info("📦 Retrieved cached results for %s", store_name)
            return [Product(**p) for p in cached_results]  # Convert cache to Product objects

        logger.info("📡 Fetching products from %s with query: %s", store_name, refined_query)

        try:
            store_config = self.store_config.get_store_config(store_name)
            rate_limit = store_config.get("rate_limit", {})

            if "requests_per_second" in rate_limit:
                await asyncio.sleep(1 / rate_limit["requests_per_second"])

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    store_config["api_url"],
                    params=refined_query,
                    headers={"Authorization": store_config["api_key"]},
                    timeout=store_config.get("timeout", 5),
                ) as response:
                    if response.status != 200:
                        logger.error("❌ %s API returned status %d", store_name, response.status)
                        return []

                    products = await response.json()
                    if not isinstance(products, list):
                        logger.error("❌ Invalid response format from %s", store_name)
                        return []

                    # Map store-specific response to common Product model
                    field_mapping = store_config.get("field_mapping", {})

                    normalized_products = []
                    for raw_product in products:
                        try:
                            normalized_product = {
                                "id": str(raw_product[field_mapping.get("id", "id")]),
                                "title": str(raw_product[field_mapping.get("title", "name")]),
                                "price": Decimal(str(raw_product[field_mapping.get("price", "price")])),
                                "store": store_name,
                                "url": str(raw_product[field_mapping.get("url", "productUrl")]),
                                "description": str(raw_product.get(field_mapping.get("description", "description"), "")),
                                "category": str(raw_product.get(field_mapping.get("category", "category"), "")),
                                "brand": str(raw_product.get(field_mapping.get("brand", "brand"), "")),
                                "image_url": str(raw_product.get(field_mapping.get("image_url", "imageUrl"), "")),
                            }
                            normalized_products.append(Product(**normalized_product))
                        except (KeyError, ValueError) as e:
                            logger.warning("⚠️ Skipping malformed product from %s: %s", store_name, str(e))
                            continue

                    if normalized_products:
                        self.redis_cache.set_cache(cache_key, [vars(p) for p in normalized_products])
                        logger.info("✅ Retrieved %d products from %s", len(normalized_products), store_name)

                    return normalized_products

        except Timeout:
            logger.error("⌛ Timeout fetching from %s", store_name)
        except RequestException as e:
            logger.error("❌ Error fetching from %s: %s", store_name, str(e))
        except (ValueError, KeyError) as e:
            logger.error("❌ Data processing error with %s: %s", store_name, str(e))

        return []

    def generate_embeddings(self, products: List[Product]) -> np.ndarray:
        """Generate AI embeddings for all products in a single batch."""
        try:
            # Combine all product info into text strings
            product_texts = [f"{p.title} {p.description or ''} {p.category or ''}" for p in products]

            # Single API call for all products
            embeddings = self.openai_service.generate_embedding(product_texts)
            return np.array(embeddings)

        except (OpenAIServiceError, ValueError) as e:
            logger.error("❌ Embedding generation failed: %s", str(e))
            # Return zero vectors if embedding fails
            return np.zeros((len(products), FAISS_VECTOR_DIMENSION))

    async def fetch_products(self, query: str):
        """Implements the complete AI-powered product search flow."""
        if not isinstance(query, str) or not query.strip():
            logger.error("❌ Invalid query provided")
            return []

        # Check final results cache first
        cache_key = f"search_results:{query.lower()}"
        cached_results = self.redis_cache.get_cache(cache_key)
        if cached_results:
            logger.info("✅ Returning cached search results")
            return cached_results

        logger.info("🔍 Starting product search for query: %s", query)

        try:
            # If not cached, perform full search
            attributes = self.query_parser.extract_product_attributes(query)
            if "error" in attributes:
                return []

            selected_stores = self.store_selector.select_best_stores(attributes)
            logger.info("🏪 Selected stores: %s", selected_stores)

            # Fetch products from all stores
            fetch_tasks = []
            for store in selected_stores:
                refined_query = self.query_parser.refine_query_for_store(query, store)
                if refined_query:
                    fetch_tasks.append(self.fetch_from_store(store, refined_query))

            store_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            all_products = [p for r in store_results if isinstance(r, list) for p in r]

            if not all_products:
                logger.warning("⚠️ No products found!")
                return []

            try:
                # Generate embeddings and rank products
                product_embeddings = self.generate_embeddings(all_products)
                query_embedding = self.openai_service.generate_embedding([query])

                self.faiss_service.add_vectors(product_embeddings)
                similar_indices = self.faiss_service.search_similar_products(query_embedding)

                if not similar_indices:
                    return all_products[:10]

                ranked_products = [
                    {**vars(all_products[idx]), "relevance_score": 1.0 - (i / len(similar_indices))} for i, idx in enumerate(similar_indices)
                ]

                # Cache the final results
                self.redis_cache.set_cache(cache_key, ranked_products)
                logger.info("✅ Returning %d ranked products", len(ranked_products))
                return ranked_products

            finally:
                if hasattr(self.faiss_service, "index"):
                    self.faiss_service.index.reset()

        except (OpenAIServiceError, FAISSIndexError) as e:
            logger.error("❌ AI service error: %s", str(e))
            return []
        except (ValueError, KeyError) as e:
            logger.error("❌ Data processing error: %s", str(e))
            return []
        except asyncio.TimeoutError as e:
            logger.error("❌ Request timeout error: %s", str(e))
            return []
