"""Factory for creating SERP service instances."""

from enum import Enum
from typing import Dict, Optional, Type

from src.services.serp_service import SerpService
from src.utils import logger


class SerpProvider(str, Enum):
    """Supported SERP API providers."""

    SERPER = "serper"  # serper.dev API
    # Add more providers here as they are implemented
    # SERPAPI = "serpapi"  # SerpAPI.com
    # SERPSTACK = "serpstack"  # SerpStack API


class SerpServiceFactory:
    """
    Factory for creating SERP service instances.

    Supports multiple API providers and centralized configuration.
    """

    _services: Dict[str, Type[SerpService]] = {
        SerpProvider.SERPER: SerpService,
        # Add more implementations here as they are created
    }

    @classmethod
    def create(cls, provider: str = SerpProvider.SERPER, api_key: Optional[str] = None, api_url: Optional[str] = None) -> SerpService:
        """
        Create a SerpService instance for the specified provider.

        Args:
            provider: SERP provider name
            api_key: Optional API key override
            api_url: Optional API URL override

        Returns:
            SerpService: Configured service instance

        Raises:
            ValueError: If provider is not supported
        """
        provider = provider.lower()

        if provider not in cls._services:
            logger.error(f"❌ Unsupported SERP provider: {provider}")
            raise ValueError(f"Unsupported SERP provider: {provider}")

        service_class = cls._services[provider]
        return service_class(api_key=api_key, api_url=api_url)
