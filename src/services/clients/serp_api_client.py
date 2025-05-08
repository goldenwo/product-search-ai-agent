"""Client for interacting with SERP APIs."""

from typing import Any, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv

from src.utils import logger
from src.utils.config import SERP_API_KEY, SERP_API_URL
from src.utils.exceptions import SerpAPIException

# Load environment variables
load_dotenv()


class SerpAPIClient:
    """
    Client for making requests to SERP API providers.

    Attributes:
        api_key: API key for the SERP provider
        api_url: Base URL for the SERP API
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        """
        Initialize SERP API client.

        Args:
            api_key: Optional API key override
            api_url: Optional API URL override
        """
        self.api_key = api_key or SERP_API_KEY
        self.api_url = api_url or SERP_API_URL

        if not self.api_key:
            logger.warning("⚠️ No SERP API key provided. API calls will fail.")

    async def search_products(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for products using the SERP API.

        Args:
            query: Search query
            num_results: Maximum number of results to return

        Returns:
            List[Dict[str, Any]]: Raw shopping results from the API

        Raises:
            SerpAPIException: If the API call fails
        """
        if not self.api_key:
            raise SerpAPIException("Missing SERP API key", "serp", 401)

        try:
            # Headers for the serper.dev API
            headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}

            # Payload for the serper.dev API
            payload = {"q": query, "num": num_results}

            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload, timeout=20) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error("❌ SERP API error: %s", error_text)
                        raise SerpAPIException(f"SERP API returned status {response.status}", "serp", response.status)

                    data = await response.json()

                    # Check remaining credits from response
                    if "credits" in data:
                        logger.info("💰 Remaining SERP API credits: %s", data.get("credits"))

                    # Extract shopping results from the response (serper.dev uses "shopping" key)
                    shopping_results = data.get("shopping", [])
                    if not shopping_results:
                        logger.warning("⚠️ No shopping results found in SERP response")
                        return []

                    if not isinstance(shopping_results, list):
                        logger.warning("⚠️ Invalid shopping results format")
                        return []

                    return shopping_results

        except aiohttp.ClientError as e:
            logger.error("❌ SERP API request failed: %s", e)
            raise SerpAPIException(f"SERP API request failed: {e}", "serp", 500) from e

        except (KeyError, ValueError, TypeError) as e:
            logger.error("❌ Error parsing SERP API response: %s", e)
            raise SerpAPIException(f"Error parsing SERP API response: {e}", "serp", 500) from e

        except Exception as e:
            logger.error("❌ Unexpected error in SERP API service: %s", e)
            raise SerpAPIException(f"Unexpected error: {e}", "serp", 500) from e
