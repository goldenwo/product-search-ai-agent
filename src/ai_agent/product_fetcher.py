import requests
from src.ai_agent.query_parser import QueryParser
from src.ai_agent.store_selector import StoreSelector
from src.ai_agent.ranking import ProductRanker
from src.services.faiss_service import FAISSService
from src.utils.config import STORE_APIS

class ProductFetcher:
    """
    Fetches real-time product data from online stores and ranks them using FAISS.
    """

    def __init__(self, faiss_service: FAISSService):
        self.store_selector = StoreSelector()
        self.rank_products = ProductRanker(faiss_service).rank_products

    def fetch_from_store(self, store_name: str, store_api_url: str, attributes: dict):
        """
        Calls the store API to fetch live product data.
        
        Args:
            store_name (str): Name of the store (Amazon, BestBuy, etc.).
            store_api_url (str): API endpoint for the store.
            attributes (dict): Extracted product attributes.
        
        Returns:
            List[dict]: List of live product data with URLs.
        """
        try:
            response = requests.get(store_api_url, params=attributes, timeout=5)
            if response.status_code == 200:
                products = response.json()
                for product in products:
                    product["store"] = store_name  # Tag the product with the store name
                return products
        except requests.RequestException as e:
            print(f"❌ Error fetching data from {store_name}: {e}")

        return []

    def fetch_products(self, query: str):
        """
        Fetches and ranks AI-enhanced product recommendations with live URLs.
        """
        # Step 1: Extract product attributes from query
        attributes = QueryParser.extract_product_attributes(query)

        # Step 2: AI selects the best stores dynamically
        selected_stores = self.store_selector.select_best_stores(attributes)

        print(f"🔹 AI Selected Stores for '{query}': {selected_stores}")

        # Step 3: Fetch live product data from selected stores
        products = []
        for store in selected_stores:
            if store in STORE_APIS:
                store_api_url = STORE_APIS[store]
                store_products = self.fetch_from_store(store, store_api_url, attributes)
                products.extend(store_products)

        # Step 4: Rank products using FAISS AI-based ranking
        ranked_products = self.rank_products(products)

        return ranked_products
