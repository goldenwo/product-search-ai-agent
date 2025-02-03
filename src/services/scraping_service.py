import requests
from src.utils.config import STORE_APIS

class ScrapingService:
    """Handles fetching product data from online stores."""
    
    def fetch_from_store(self, store: str, attributes: dict):
        """Fetches product data from the selected store based on attributes."""
        url = STORE_APIS.get(store)
        if not url:
            return []

        response = requests.get(url, params=attributes)
        return response.json() if response.status_code == 200 else []
