"""Service for enriching products with detailed specifications."""

import asyncio
import json
import re
from typing import Any, Dict, Optional

import aiohttp
import extruct
from bs4 import BeautifulSoup, Tag
from playwright.async_api import async_playwright
from w3lib.html import get_base_url

from src.models.product import Product
from src.services.openai_service import OpenAIService
from src.utils import logger
from src.utils.config import ENRICHMENT_USE_HEADLESS_FALLBACK, HEADLESS_BROWSER_ENDPOINT, OPENAI_EXTRACTION_MODEL


class ProductEnricher:
    """
    Service for enriching products with detailed specifications.

    Uses a multi-tier approach:
    1. Extracts structured data (JSON-LD, Microdata, OpenGraph)
    2. Falls back to AI-powered extraction from HTML for details.
    """

    def __init__(self, openai_service: OpenAIService):
        """Initialize the product enricher service with dependencies."""
        self.openai_service = openai_service

        # Common headers to simulate a browser
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

    async def get_product_specs(self, product_id: str, product_url: str, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve detailed specifications for a product.

        Args:
            product_id: Product identifier
            product_url: URL to the product page
            name: Optional product name for context

        Returns:
            Dict[str, Any]: Product specifications
        """
        logger.info("🔍 Fetching specifications for product: %s", name or product_id)

        # Check if URL is valid
        if not product_url or not product_url.startswith(("http://", "https://")):
            logger.warning("⚠️ Invalid product URL: %s", product_url)
            return {}

        try:
            # Fetch HTML content from product page
            html_content = await self._fetch_product_page(product_url)

            if not html_content:
                logger.warning("⚠️ Failed to fetch product page: %s", product_url)
                return {}

            # Extract specifications from HTML
            specs = await self._extract_specifications(html_content, product_url, name)

            # Add product identity information
            specs["product_id"] = product_id
            if name and "name" not in specs:
                specs["name"] = name

            return specs

        except Exception as e:
            logger.error("❌ Error fetching product specifications: %s", str(e))
            return {}

    async def enrich_product(self, product: Product) -> Product:
        """
        Enrich a Product object with detailed specifications from its URL.

        Args:
            product: Product object to enrich

        Returns:
            Product: Enriched product with updated fields
        """
        try:
            if not product.url:
                logger.warning("⚠️ Cannot enrich product without URL")
                return product

            # Fetch specifications
            specs = await self.get_product_specs(product_id=product.id, product_url=str(product.url), name=product.title)

            if not specs:
                logger.warning("⚠️ No specifications found for product: %s", product.title)
                return product

            # Update product with extracted data
            enriched_product = self._update_product_from_specs(product, specs)
            logger.info("✅ Successfully enriched product: %s", product.title)
            return enriched_product

        except Exception as e:
            # Log specific error during enrichment process
            logger.error("❌ Error during enrichment for product %s (%s): %s", product.id, product.url, str(e))
            return product  # Return original product on failure

    def _update_product_from_specs(self, product: Product, specs: Dict[str, Any]) -> Product:
        """
        Update a Product object with extracted specifications.

        Prioritizes existing product data unless the new data is clearly better
        (e.g., longer description, more detailed specs).

        Args:
            product: Original Product object
            specs: Extracted specifications

        Returns:
            Updated Product object
        """
        # Ensure specifications dictionary exists
        if product.specifications is None:
            product.specifications = {}

        # Helper function to check if a value is considered "empty" or non-informative
        def is_empty(value):
            return value is None or value == "" or str(value).lower() == "unknown" or str(value).lower() == "n/a"

        # Map structured data fields carefully, avoiding overwriting good data
        # Overwrite only if the existing value is empty/uninformative
        if "brand" in specs and specs["brand"] and is_empty(product.brand):
            product.brand = str(specs["brand"]).strip()

        # Only update description if the new one is significantly longer/more detailed
        if "description" in specs and specs["description"]:
            new_desc = str(specs["description"]).strip()
            old_desc_len = len(product.description or "")
            # Use relative length check and absolute minimum improvement
            if len(new_desc) > old_desc_len * 1.2 and len(new_desc) > old_desc_len + 50:
                product.description = new_desc
            elif is_empty(product.description) and len(new_desc) > 20:
                product.description = new_desc  # Populate if empty

        if "category" in specs and specs["category"] and is_empty(product.category):
            product.category = str(specs["category"]).strip()

        # Update rating/reviews only if missing
        if "rating" in specs and specs["rating"] and is_empty(product.rating):
            try:
                rating_val = float(specs["rating"])
                if 0 <= rating_val <= 5:  # Basic validation
                    product.rating = rating_val
            except (ValueError, TypeError):
                pass
        if "reviewCount" in specs and specs["reviewCount"] and is_empty(product.review_count):
            try:
                review_count_val = int(specs["reviewCount"])
                if review_count_val >= 0:
                    product.review_count = review_count_val
            except (ValueError, TypeError):
                pass

        # Process specifications provided by AI (if structure is correct)
        ai_specs_dict = specs.get("specifications")
        if isinstance(ai_specs_dict, dict):
            for key, value in ai_specs_dict.items():
                clean_key = str(key).strip()
                clean_value = str(value).strip()
                # Add if key is new and value is not empty
                if clean_key and clean_value and clean_key not in product.specifications:
                    product.specifications[clean_key] = clean_value

        # Process features provided by AI
        ai_features_list = specs.get("features")
        if isinstance(ai_features_list, list):
            valid_features = [str(f).strip() for f in ai_features_list if str(f).strip()]
            if valid_features and is_empty(product.specifications.get("Features")):
                product.specifications["Features"] = ", ".join(valid_features)

        # Re-validate to ensure type consistency after updates
        try:
            product_dict = product.model_dump()
            return Product.model_validate(product_dict)
        except Exception as e:
            logger.error("❌ Validation error after updating product %s: %s", product.id, str(e))
            return product  # Return original on validation error

    async def _fetch_product_page(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from product page, with optional headless browser fallback.

        Args:
            url: Product page URL

        Returns:
            Optional[str]: HTML content or None if failed
        """
        html_content = None
        # Attempt 1: Standard HTTP fetch
        logger.debug(f"Attempting standard fetch for: {url}")
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=10, allow_redirects=True) as response:
                    if 200 <= response.status < 300:
                        try:
                            html_content = await response.text(encoding="utf-8", errors="ignore")
                            logger.debug(f"Standard fetch successful for: {url}")
                        except UnicodeDecodeError:
                            try:
                                detected_encoding = response.get_encoding()
                                html_content = await response.text(encoding=detected_encoding, errors="ignore")
                                logger.debug(f"Standard fetch successful (fallback encoding) for: {url}")
                            except Exception as decode_err:
                                logger.error(f"❌ Final decode failed for {url}: {decode_err}")
                        # Check if content seems minimal (might indicate JS needed)
                        if html_content and len(html_content) < 1000:  # Arbitrary threshold
                            logger.warning(f"⚠️ Standard fetch for {url} resulted in very short content ({len(html_content)} bytes). May require JS.")
                            # Optionally clear content to trigger fallback if enabled
                            # html_content = None
                    else:
                        logger.warning(f"⚠️ Standard fetch failed for {url}, status: {response.status}")

        except asyncio.TimeoutError:
            logger.warning(f"⏰ Timeout during standard fetch for: {url}")
        except aiohttp.ClientError as e:
            logger.error(f"❌ HTTP client error during standard fetch for {url}: {type(e).__name__} - {str(e)}")
        except Exception as e:
            logger.error(f"❌ Unexpected error during standard fetch for {url}: {type(e).__name__} - {str(e)}")

        # Attempt 2: Headless browser fallback (if enabled and needed)
        if html_content is None and ENRICHMENT_USE_HEADLESS_FALLBACK:
            logger.info(f"🚀 Standard fetch failed or insufficient for {url}, attempting headless browser fallback...")
            try:
                async with async_playwright() as p:
                    browser = None
                    connect_args = {}
                    if HEADLESS_BROWSER_ENDPOINT:
                        logger.debug(f"Connecting to remote browser: {HEADLESS_BROWSER_ENDPOINT}")
                        # Add headers or other args if needed for remote service auth
                        browser = await p.chromium.connect_over_cdp(HEADLESS_BROWSER_ENDPOINT, **connect_args)
                    else:
                        logger.debug("Launching local headless browser...")
                        browser = await p.chromium.launch()

                    page = await browser.new_page(user_agent=self.headers["User-Agent"])
                    # Increased navigation timeout
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")  # Wait for DOM, JS might still run
                    # Optional: Add a small delay or wait for a specific selector if needed
                    # await page.wait_for_timeout(2000)
                    html_content = await page.content()
                    await browser.close()
                    logger.info(f"✅ Headless browser fetch successful for: {url}")
            except Exception as e:
                logger.error(f"❌ Headless browser fallback failed for {url}: {type(e).__name__} - {str(e)}")
                html_content = None  # Ensure content is None if fallback fails
        elif html_content is None:
            logger.warning(f"⚠️ Standard fetch failed for {url} and headless fallback is disabled.")

        return html_content

    async def _extract_specifications(self, html_content: str, url: str, product_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract product specifications using a tiered approach.
        1. Try extracting structured data first (fast and reliable)
        2. Check if structured data is sufficient
        3. If not sufficient, fall back to AI extraction

        Args:
            html_content: HTML content from product page
            url: URL of the product page for base URL resolution
            product_name: Optional product name for context

        Returns:
            Dict[str, Any]: Extracted product specifications
        """
        all_specs = {}
        try:
            # 1. Try extracting structured data first (fast and reliable)
            structured_data = self._extract_structured_data(html_content, url)
            if structured_data:
                all_specs.update(structured_data)
                logger.info("✅ Extracted structured data for %s", product_name or url)

            # 2. Check if structured data is sufficient
            if self._is_sufficiently_detailed(all_specs):
                logger.info("✅ Structured data sufficient for %s", product_name or url)
                return all_specs

            # 3. If not sufficient, fall back to AI extraction
            logger.info("ℹ️ Structured data insufficient, attempting AI extraction for %s", product_name or url)
            # Add a small delay before hitting AI
            await asyncio.sleep(0.1)
            ai_specs = await self._extract_specs_with_ai(html_content, product_name)

            # Merge AI specs, prioritizing existing structured data keys
            if ai_specs:
                # Merge specifications dictionary intelligently
                if isinstance(ai_specs.get("specifications"), dict) and isinstance(all_specs.get("specifications"), dict):
                    # Prioritize existing keys from structured data, add new ones from AI
                    merged_sub_specs = {**ai_specs["specifications"], **all_specs["specifications"]}
                    all_specs["specifications"] = merged_sub_specs
                elif isinstance(ai_specs.get("specifications"), dict):
                    all_specs["specifications"] = ai_specs["specifications"]

                # Merge other top-level keys provided by AI (brand, category, description, features)
                # The _update_product_from_specs method will handle the merging logic carefully
                for key in ["brand", "category", "description", "features"]:
                    if key in ai_specs and ai_specs[key]:
                        # Store AI value temporarily; merge logic is in update method
                        all_specs[f"ai_{key}"] = ai_specs[key]

            # Clean up temporary keys before returning final specs for update method
            final_specs_for_update = {k: v for k, v in all_specs.items() if not k.startswith("ai_")}
            if "ai_brand" in all_specs:
                final_specs_for_update["brand"] = all_specs["ai_brand"]
            if "ai_category" in all_specs:
                final_specs_for_update["category"] = all_specs["ai_category"]
            if "ai_description" in all_specs:
                final_specs_for_update["description"] = all_specs["ai_description"]
            if "ai_features" in all_specs:
                final_specs_for_update["features"] = all_specs["ai_features"]

            # If AI extraction happened, log the final count of top-level keys
            if ai_specs:
                logger.info("ℹ️ Combined specs ready for update for %s (Keys: %d)", product_name or url, len(final_specs_for_update))

            return final_specs_for_update

        except Exception as e:
            logger.error("❌ Error extracting specifications for %s: %s", product_name or url, str(e))
            return all_specs  # Return whatever was gathered, even if partial

    def _is_sufficiently_detailed(self, specs: Dict[str, Any]) -> bool:
        """Check if extracted data is detailed enough to skip AI."""
        # Example criteria: has a description and at least 3 other specification keys
        has_desc = bool(specs.get("description") and len(str(specs["description"])) > 50)
        # Count relevant spec keys (excluding common top-level ones)
        spec_keys = [
            k for k in specs.keys() if k not in ["name", "brand", "description", "category", "price", "url", "image", "@type", "@context", "offers"]
        ]
        has_enough_specs = len(spec_keys) >= 3
        return has_desc and has_enough_specs

    def _extract_structured_data(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Extract structured product data using extruct.

        Args:
            html_content: HTML content from product page
            url: URL of the product page for base URL resolution

        Returns:
            Dict[str, Any]: Structured product specifications
        """
        try:
            base_url = get_base_url(html_content, url)
            metadata = extruct.extract(html_content, base_url=base_url, uniform=True, syntaxes=["json-ld", "microdata", "opengraph"])

            specs = {}

            # Process JSON-LD data (highest priority)
            for item in metadata.get("json-ld", []):
                if item.get("@type") == "Product" or item.get("@type") == "http://schema.org/Product":
                    # Extract product properties
                    if "name" in item:
                        specs["name"] = item["name"]
                    if "brand" in item:
                        if isinstance(item["brand"], dict):
                            specs["brand"] = item["brand"].get("name")
                        else:
                            specs["brand"] = item["brand"]
                    if "description" in item:
                        specs["description"] = item["description"]
                    if "sku" in item:
                        specs["sku"] = item["sku"]
                    if "mpn" in item:
                        specs["mpn"] = item["mpn"]
                    if "model" in item:
                        specs["model"] = item["model"]

                    # Extract detailed specs from product properties
                    for key, value in item.items():
                        if key not in ["@context", "@type", "image", "url", "offers"]:
                            specs[key] = value

                    # Process offers data
                    if "offers" in item:
                        offer = item["offers"]
                        if isinstance(offer, dict):
                            if "price" in offer:
                                specs["price"] = offer["price"]
                            if "availability" in offer:
                                specs["availability"] = offer["availability"]
                            if "itemCondition" in offer:
                                specs["condition"] = offer["itemCondition"]
                        elif isinstance(offer, list) and offer:
                            # Sometimes offers is a list, take the first one
                            first_offer = offer[0]
                            if isinstance(first_offer, dict):
                                if "price" in first_offer:
                                    specs["price"] = first_offer["price"]
                                if "availability" in first_offer:
                                    specs["availability"] = first_offer["availability"]

            # Process microdata (second priority)
            if len(specs) < 3:
                for item in metadata.get("microdata", []):
                    if item.get("type") == "https://schema.org/Product" or item.get("type") == "http://schema.org/Product":
                        props = item.get("properties", {})
                        for key, value in props.items():
                            if isinstance(value, list) and value:
                                specs[key] = value[0]
                            else:
                                specs[key] = value

            # Process OpenGraph data (third priority)
            # Fix: OpenGraph data can be a list of dictionaries or a dictionary
            if len(specs) < 3:
                og_data = metadata.get("opengraph", [])

                # Handle different OpenGraph data formats
                if isinstance(og_data, dict):
                    self._extract_opengraph_dict(og_data, specs)
                elif isinstance(og_data, list) and og_data and isinstance(og_data[0], dict):
                    self._extract_opengraph_dict(og_data[0], specs)

            return specs

        except Exception as e:
            logger.warning("⚠️ Error extracting structured data: %s", str(e))
            return {}

    def _extract_opengraph_dict(self, og_dict: dict, specs: dict) -> None:
        """Extract data from OpenGraph dictionary."""
        # Access values safely with get() method
        if "og:title" in og_dict and "name" not in specs:
            specs["name"] = og_dict.get("og:title")
        if "og:description" in og_dict and "description" not in specs:
            specs["description"] = og_dict.get("og:description")
        if "og:brand" in og_dict and "brand" not in specs:
            specs["brand"] = og_dict.get("og:brand")
        if "og:price:amount" in og_dict and "price" not in specs:
            specs["price"] = og_dict.get("og:price:amount")
        if "og:price:currency" in og_dict and "currency" not in specs:
            specs["currency"] = og_dict.get("og:price:currency")
        if "og:availability" in og_dict and "availability" not in specs:
            specs["availability"] = og_dict.get("og:availability")

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize text content.

        Args:
            text: Raw text content

        Returns:
            str: Cleaned text
        """
        # Remove extra whitespace and normalize
        cleaned = re.sub(r"\s+", " ", text).strip()
        # Basic HTML entity decoding (might need more robust library like html.unescape)
        cleaned = cleaned.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        return cleaned

    async def _extract_specs_with_ai(self, html_content: str, product_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Use AI to extract specifications from HTML when structured data isn't found or sufficient.
        Uses JSON mode for more reliable output.

        Args:
            html_content: HTML content from product page
            product_name: Optional product name for context

        Returns:
            Dict[str, Any]: Extracted specifications as a dictionary
        """
        try:
            # --- Improved HTML Cleaning & Content Extraction ---
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove common non-content elements more aggressively
            for selector in [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "aside",
                ".sidebar",
                ".related-products",
                ".upsell",
                "form",
                "button",
                "input",
                "select",
                ".breadcrumb",
                ".pagination",
                "iframe",
                "noscript",
                "link",
                "meta",
            ]:
                for element in soup.select(selector):
                    if isinstance(element, Tag):
                        element.extract()

            # --- Targeted Content Extraction ---
            extracted_texts = []

            # Common selectors for different parts of the product page
            content_selectors = {
                "description": ["#productDescription", ".product-description", "#description", ".description", ".product-long-description"],
                "specifications": [
                    "#productDetails_detailBullets_sections1",
                    ".specification-table",
                    ".product-specs",
                    ".specifications",
                    "#technicalSpecifications_feature_div",
                    ".prodDetTable",
                ],
                "features": [".feature-bullets", ".product-features", ".key-features", "#feature-bullets"],
                "main_content": ["main", "#main", "#content", ".content", "#product-details", ".product-info", "article"],  # Fallback
            }

            processed_elements = set()

            # Extract from specific sections first
            for section_name, selectors in content_selectors.items():
                if section_name == "main_content":
                    continue  # Handle fallback later
                for selector in selectors:
                    elements = soup.select(selector)
                    for element in elements:
                        if isinstance(element, Tag) and element not in processed_elements:
                            # Extract text, maybe add a section header
                            section_text = element.get_text(separator="\n", strip=True)
                            if section_text:
                                extracted_texts.append(
                                    f"\n--- START {section_name.upper()} SECTION ---\n{section_text}\n--- END {section_name.upper()} SECTION ---\n"
                                )
                                processed_elements.add(element)
                            # Optionally remove the processed element to avoid duplication if using fallback
                            # element.extract()

            # If few specific sections found, try main content area
            if len(extracted_texts) < 2:
                logger.info("Few specific sections found, extracting from main content area for %s", product_name or "page")
                for selector in content_selectors["main_content"]:
                    main_element = soup.select_one(selector)
                    if main_element and isinstance(main_element, Tag) and main_element not in processed_elements:
                        main_text = main_element.get_text(separator="\n", strip=True)
                        if main_text:
                            extracted_texts.append(f"\n--- START MAIN CONTENT ---\n{main_text}\n--- END MAIN CONTENT ---\n")
                            break  # Found main content, stop looking

            # Combine extracted texts
            final_text = "\n\n".join(extracted_texts)

            if not final_text:
                # If absolutely nothing found, fallback to body text (less ideal)
                logger.warning("⚠️ Could not extract targeted sections for %s, falling back to full body text.", product_name or "page")
                body = soup.find("body")
                final_text = body.get_text(separator="\n", strip=True) if body else ""

            # Further clean the combined text (remove excessive newlines)
            cleaned_text = re.sub(r"\n{3,}", "\n\n", final_text).strip()
            # --- End Targeted Content Extraction ---

            if not cleaned_text:
                logger.error("❌ No processable text content found after cleaning for %s", product_name or "page")
                return {}

            # Limit text length for API efficiency (apply after cleaning)
            max_len = 15000  # Keep token limit reasonable
            if len(cleaned_text) > max_len:
                text_to_send = cleaned_text[:max_len] + "\n... (truncated due to length)"
                logger.warning("⚠️ Truncated targeted text content for AI extraction for %s (Sent %d chars)", product_name or "product", max_len)
            else:
                text_to_send = cleaned_text
                logger.info("ℹ️ Sending %d chars of targeted text to AI for %s", len(text_to_send), product_name or "product")

            # Create AI prompt for structured extraction (Ensure it explicitly asks for JSON)
            context = f' for the product named "{product_name}"' if product_name else ""
            prompt = f"""Analyze the following text content extracted from specific sections of a product page{context}.
Your task is to extract key product information accurately.

**Instructions:**
1.  Parse the provided text (organized by sections like DESCRIPTION, SPECIFICATIONS, FEATURES) to identify the main product description.
2.  Extract technical specifications into a JSON object where keys are spec names and values are the spec details 
    (e.g., {{"Screen Size": "14 inch", "RAM": "16GB"}}).
3.  Extract a list of key product features or selling points as an array of strings.
4.  Identify the product brand and primary category.
5.  **You MUST return ONLY a single, valid JSON object.** Do not include any text before or after the JSON.
6.  Use the following exact keys in your JSON output: "description", "specifications", "features", "brand", "category".
7.  If a piece of information cannot be found reliably, 
    use `null` for string fields, 
    `{{}}` for the specifications object,
    or `[]` for the features list.

**Extracted Product Page Content:**
```
{text_to_send}
```

**JSON Output:**
"""

            # Use JSON mode
            response = self.openai_service.generate_response(
                prompt,
                model=OPENAI_EXTRACTION_MODEL,  # Use dedicated model from config
                max_tokens=2000,
                use_json_mode=True,  # Enable JSON mode
            )

            # Parse JSON response (should be more reliable now)
            try:
                # JSON mode *should* guarantee valid JSON string
                specs = json.loads(response)
                if not isinstance(specs, dict):
                    logger.error("❌ AI JSON mode response was not a dict for %s. Response: %s", product_name or "product", response[:500])
                    return {}

                # Optional: Basic validation of expected keys
                expected_keys = {"description", "specifications", "features", "brand", "category"}
                if not expected_keys.issubset(specs.keys()):
                    logger.warning("⚠️ AI JSON response missing expected keys for %s. Found: %s", product_name or "product", list(specs.keys()))
                    # Proceed anyway, but log warning

                logger.info("✅ Successfully extracted data with AI (JSON Mode) for %s", product_name or "product")
                return specs

            except json.JSONDecodeError as e:
                # This should be less common with JSON mode, but handle just in case
                logger.error("❌ Failed to parse AI JSON mode response for %s: %s\nResponse: %s", product_name or "product", str(e), response[:500])
                return {}

        except Exception as e:
            logger.error("❌ Error using AI to extract specifications for %s: %s", product_name or "product", str(e))
            return {}  # Return empty dict on failure
