"""Product fetcher service that coordinates the AI-powered product search workflow."""

import time
from typing import Dict

import numpy as np
import requests

from src.ai_agent.query_parser import QueryParser
from src.ai_agent.store_selector import StoreSelector
from src.services.faiss_service import FAISSService
from src.services.openai_service import OpenAIService
from src.utils import logger
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

    def generate_embeddings(self, products: list) -> np.ndarray:
        """Generate AI embeddings for products."""
        # This would use OpenAI or another embedding service
        embeddings = []
        for product in products:
            product_text = f"{product['name']} {product.get('description', '')}"
            embedding = self.openai_service.generate_embedding(product_text)
            embeddings.append(embedding)
        return np.array(embeddings)

    def fetch_from_store(self, store_name: str, refined_query: Dict[str, str]):
        """Fetch products from store API with refined query."""
        store_name = store_name.lower()
        logger.info("📡 Fetching products from %s with attributes: %s", store_name, refined_query)

        try:
            # Get store config including API URL and key
            store_config = self.store_config.get_store_config(store_name)
            rate_limit = store_config.get("rate_limit", {})

            if "requests_per_second" in rate_limit:
                time.sleep(1 / rate_limit["requests_per_second"])  # Basic rate limiting

            # Validate query params against allowed params
            allowed_params = self.store_config.get_allowed_params(store_name)
            validated_query = {k: v for k, v in refined_query.items() if k in allowed_params}

            # Make API request with store-specific config
            response = requests.get(
                store_config["api_url"],
                params=validated_query,
                headers={"Authorization": store_config["api_key"]},
                timeout=store_config.get("timeout", 5),
            )
            if response.status_code == 200:
                products = response.json()
                for product in products:
                    product["store"] = store_name
                logger.info("✅ Retrieved %d products from %s", len(products), store_name)
                return products
        except requests.RequestException as e:
            logger.error("❌ Error fetching data from %s: %s", store_name, e)

        return []

    def fetch_products(self, query: str):
        """Implements the complete AI-powered product search flow."""
        logger.info("🔍 Starting product search for query: %s", query)

        # 1. Parse query for attributes
        attributes = self.query_parser.extract_product_attributes(query)
        if "error" in attributes:
            return []

        # 2. Select relevant stores
        selected_stores = self.store_selector.select_best_stores(attributes)
        logger.info("🏪 Selected stores: %s", selected_stores)

        # 3. Refine query for each store
        all_products = []
        for store in selected_stores:
            refined_query = self.query_parser.refine_query_for_store(query, store)
            if not refined_query:  # Skip store if refinement failed
                logger.warning("⚠️ Skipping %s due to query refinement failure", store)
                continue
            store_products = self.fetch_from_store(store, refined_query)
            all_products.extend(store_products)

        if not all_products:
            logger.warning("⚠️ No products found!")
            return []

        # 4. Generate AI embeddings for products
        product_embeddings = self.generate_embeddings(all_products)

        # 5. Index products in FAISS
        self.faiss_service.add_vectors(product_embeddings)

        # 6. Generate query embedding for FAISS search
        query_embedding = self.openai_service.generate_embedding(query)

        # 7. Find most relevant products using FAISS
        similar_indices = self.faiss_service.search_similar_products(query_embedding)

        # 8. Get matched products and rank by relevance
        if not similar_indices:
            return []

        ranked_products = [{**all_products[idx], "relevance_score": 1.0 - (i / len(similar_indices))} for i, idx in enumerate(similar_indices)]

        logger.info("✅ Returning %d ranked products", len(ranked_products))
        return ranked_products
