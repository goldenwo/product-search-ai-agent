"""Store configuration management with API settings and parameters."""

import json
from pathlib import Path
from typing import Any, Dict, List

import src.utils.config as config  # Import as module
from src.utils import logger


class StoreConfig:
    """
    Manages store-specific configurations and API settings.

    Attributes:
        store_configs: Dictionary of store configurations
            - API URLs
            - Authentication
            - Rate limits
            - Parameter mappings
    """

    def __init__(self):
        # Move configs inside src directory
        self.config_dir = Path(__file__).parent.parent / "store_configs" / "stores"
        self.store_configs = {}
        self._load_store_configs()

    def _load_store_configs(self) -> None:
        """Load all store configurations from JSON files."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        for config_file in self.config_dir.glob("*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    store_config = json.load(f)
                    store_name = config_file.stem.lower()  # Use lowercase for consistency

                    # Validate required fields
                    required_fields = {"name", "api_url", "allowed_params"}
                    if not all(field in store_config for field in required_fields):
                        logger.error("❌ Missing required fields in %s", config_file.name)
                        continue

                    self.store_configs[store_name] = store_config
                    logger.info("✅ Loaded config for %s", store_config["name"])

            except json.JSONDecodeError as e:
                logger.error("❌ Invalid JSON in %s: %s", config_file.name, e)
            except (IOError, OSError) as e:
                logger.error("❌ Error reading %s: %s", config_file.name, e)

    def get_allowed_params(self, store_name: str) -> List[str]:
        """
        Get allowed API parameters for store.

        Args:
            store_name: Name of store to get parameters for

        Returns:
            List[str]: List of valid parameter names for store API
        """
        if store_name not in self.store_configs:
            return ["keywords"]
        return list(self.store_configs[store_name].get("allowed_params", ["keywords"]))

    def get_store_config(self, store_name: str) -> Dict[str, Any]:
        """
        Get configuration for specific store.

        Args:
            store_name: Name of store to get config for

        Returns:
            Dict[str, Any]: Store configuration including API details
            Empty dict if store not found

        Example:
            {
                "api_url": "https://api.store.com",
                "api_key": "key123",
                "rate_limit": {"requests_per_second": 5},
                "timeout": 10
            }
        """
        store_name = store_name.lower()
        if store_name not in self.store_configs:
            raise ValueError(f"No configuration found for store: {store_name}")

        store_config = self.store_configs[store_name].copy()
        # Add dynamic values from environment, falling back to default_api_url
        store_config["api_url"] = config.get_store_api_url(store_name, default_url=store_config.get("default_api_url"))
        store_config["api_key"] = config.get_store_api_key(store_name)

        return store_config
