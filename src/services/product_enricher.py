"""Service for enriching products with detailed specifications."""

import asyncio
import json
import re
from typing import Any, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup, Tag
import extruct
from playwright.async_api import async_playwright
from w3lib.html import get_base_url

from src.models.product import Product
from src.services.openai_service import OpenAIService
from src.utils import logger
from src.utils.config import ENRICHMENT_USE_HEADLESS_FALLBACK, HEADLESS_BROWSER_ENDPOINT, OPENAI_EXTRACTION_MODEL

# --- Constants for Scraping/Parsing ---

# Selectors for common non-content elements to remove before AI processing
_NON_CONTENT_SELECTORS = [
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
]

# Selectors for likely content sections on product pages
_CONTENT_SELECTORS = {
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
    "main_content": ["main", "#main", "#content", ".content", "#product-details", ".product-info", "article"],  # Fallback selectors
}

# Keys often found in structured data (JSON-LD/Microdata) that are NOT detailed specs
_EXCLUDED_STRUCTURED_DATA_KEYS = {
    "name",
    "brand",
    "description",
    "category",
    "price",
    "url",
    "image",
    "@type",
    "@context",
    "offers",
    "availability",
    "condition",
    "currency",
    "sku",
    "mpn",
    "gtin",
}

# --- End Constants ---


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

        # Common headers to simulate a browser during HTTP requests
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
        Retrieve detailed specifications for a product by fetching and parsing its page.

        Args:
            product_id: Product identifier (used for logging and potentially cache keys)
            product_url: URL to the product page
            name: Optional product name for context

        Returns:
            Dict[str, Any]: Product specifications
        """
        logger.info("🔍 Fetching specifications for product: %s", name or product_id)

        if not product_url or not product_url.startswith(("http://", "https://")):
            logger.warning("⚠️ Invalid product URL: %s", product_url)
            return {}

        try:
            # Fetch HTML content from product page (with potential headless fallback)
            html_content = await self._fetch_product_page(product_url)

            if not html_content:
                logger.warning("⚠️ Failed to fetch product page: %s", product_url)
                return {}

            # Extract specifications from HTML (structured data -> AI fallback)
            specs = await self._extract_specifications(html_content, product_url, name)

            # Add product identity information if not already present from extraction
            if "product_id" not in specs:
                specs["product_id"] = product_id
            if name and "name" not in specs:
                specs["name"] = name

            return specs

        except Exception as e:
            logger.error("❌ Error fetching product specifications for %s: %s", product_url, e)
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
            # Log specific error during the enrichment workflow
            logger.error("❌ Error during enrichment for product %s (%s): %s", product.id, product.url, e)
            return product  # Return original product on failure

    def _update_product_from_specs(self, product: Product, specs: Dict[str, Any]) -> Product:
        """
        Update a Product object with extracted specifications.

        Prioritizes existing product data unless the new data is clearly better
        (e.g., longer description, more detailed specs, or filling missing fields).

        Args:
            product: Original Product object
            specs: Extracted specifications

        Returns:
            Updated Product object
        """
        # Ensure specifications dictionary exists
        if product.specifications is None:
            product.specifications = {}

        # Helper to check if a value is considered "empty" or uninformative
        def is_empty(value):
            return value is None or value == "" or str(value).lower() == "unknown" or str(value).lower() == "n/a"

        # Update fields only if the existing value is empty/uninformative or new data is better
        if "brand" in specs and specs["brand"] and is_empty(product.brand):
            product.brand = str(specs["brand"]).strip()

        # Only update description if the new one is significantly better or fills a gap
        if "description" in specs and specs["description"]:
            new_desc = str(specs["description"]).strip()
            old_desc_len = len(product.description or "")
            # Criteria: significantly longer (relative + absolute) OR filling an empty description
            if (len(new_desc) > old_desc_len * 1.2 and len(new_desc) > old_desc_len + 50) or (is_empty(product.description) and len(new_desc) > 20):
                product.description = new_desc

        if "category" in specs and specs["category"] and is_empty(product.category):
            product.category = str(specs["category"]).strip()

        # Update rating/reviews only if missing from original product
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
                pass  # Ignore if review count is invalid

        # Merge specifications dictionary provided by AI
        ai_specs_dict = specs.get("specifications")
        if isinstance(ai_specs_dict, dict):
            for key, value in ai_specs_dict.items():
                clean_key = str(key).strip()
                clean_value = str(value).strip()
                # Add if key is new and value is not empty
                if clean_key and clean_value and clean_key not in product.specifications:
                    product.specifications[clean_key] = clean_value

        # Merge features list provided by AI (stored under a 'Features' key in specs)
        ai_features_list = specs.get("features")
        if isinstance(ai_features_list, list):
            valid_features = [str(f).strip() for f in ai_features_list if str(f).strip()]
            # Add features only if the 'Features' spec doesn't already exist
            if valid_features and is_empty(product.specifications.get("Features")):
                product.specifications["Features"] = ", ".join(valid_features)

        # Re-validate the updated product model
        try:
            product_dict = product.model_dump()
            return Product.model_validate(product_dict)
        except Exception as e:
            logger.error("❌ Validation error after updating product %s: %s", product.id, e)
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
        # Attempt 1: Standard HTTP fetch with aiohttp
        logger.debug("Attempting standard fetch for: %s", url)
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=10, allow_redirects=True) as response:
                    if 200 <= response.status < 300:
                        try:
                            # Attempt decoding with utf-8 first
                            html_content = await response.text(encoding="utf-8", errors="ignore")
                            logger.debug("Standard fetch successful for: %s", url)
                        except UnicodeDecodeError:
                            # Fallback to detected encoding if utf-8 fails
                            try:
                                detected_encoding = response.get_encoding()
                                html_content = await response.text(encoding=detected_encoding, errors="ignore")
                                logger.debug("Standard fetch successful (fallback encoding: %s) for: %s", detected_encoding, url)
                            except Exception as decode_err:
                                logger.error("❌ Final decode failed for %s: %s", url, decode_err)
                        # Check if content seems minimal (might indicate JS rendering required)
                        if html_content and len(html_content) < 1000:  # Arbitrary threshold
                            logger.warning("⚠️ Standard fetch for %s resulted in short content (%d bytes). May require JS.", url, len(html_content))
                            # If fallback enabled, setting html_content to None here would force it
                            # html_content = None
                    else:
                        logger.warning("⚠️ Standard fetch failed for %s, status: %d", url, response.status)

        except asyncio.TimeoutError:
            logger.warning("⏰ Timeout during standard fetch for: %s", url)
        except aiohttp.ClientError as e:
            logger.error("❌ HTTP client error during standard fetch for %s: %s - %s", url, type(e).__name__, e)
        except Exception as e:
            logger.error("❌ Unexpected error during standard fetch for %s: %s - %s", url, type(e).__name__, e)

        # Attempt 2: Headless browser fallback (if enabled and standard fetch failed/insufficient)
        if html_content is None and ENRICHMENT_USE_HEADLESS_FALLBACK:
            logger.info("🚀 Standard fetch failed or insufficient for %s, attempting headless browser fallback...", url)
            try:
                async with async_playwright() as p:
                    browser = None
                    connect_args = {}
                    if HEADLESS_BROWSER_ENDPOINT:
                        logger.debug("Connecting to remote browser: %s", HEADLESS_BROWSER_ENDPOINT)
                        # Add headers or other connection args if needed for remote service auth
                        browser = await p.chromium.connect_over_cdp(HEADLESS_BROWSER_ENDPOINT, **connect_args)
                    else:
                        logger.debug("Launching local headless browser...")
                        browser = await p.chromium.launch()

                    page = await browser.new_page(user_agent=self.headers["User-Agent"])
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")  # Wait for DOM, JS might still run
                    # Optional: Add delay or wait for specific selector if needed for heavy JS sites
                    # await page.wait_for_timeout(2000)
                    html_content = await page.content()
                    await browser.close()
                    logger.info("✅ Headless browser fetch successful for: %s", url)
            except Exception as e:
                logger.error("❌ Headless browser fallback failed for %s: %s - %s", url, type(e).__name__, e)
                html_content = None  # Ensure content is None if fallback fails
        elif html_content is None:
            logger.warning("⚠️ Standard fetch failed for %s and headless fallback is disabled.", url)

        return html_content

    async def _extract_specifications(self, html_content: str, url: str, product_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract product specifications using a tiered approach.
        1. Try extracting structured data first (fast, reliable)
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
            # 1. Try extracting structured data first (fast, reliable)
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
            # Add a small delay before hitting AI to be polite
            await asyncio.sleep(0.1)
            ai_specs = await self._extract_specs_with_ai(html_content, product_name)

            # Merge AI specs, prioritizing existing structured data keys where overlaps occur
            if ai_specs:
                # Merge 'specifications' dictionary intelligently
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
                        # Store AI value temporarily; final merge/overwrite logic is in _update_product_from_specs
                        all_specs[f"ai_{key}"] = ai_specs[key]

            # Prepare final specs dict for the update method by resolving temporary AI keys
            # This ensures the update method gets a clean dict with the intended final values
            final_specs_for_update = {k: v for k, v in all_specs.items() if not k.startswith("ai_")}
            if "ai_brand" in all_specs:
                final_specs_for_update["brand"] = all_specs["ai_brand"]
            if "ai_category" in all_specs:
                final_specs_for_update["category"] = all_specs["ai_category"]
            if "ai_description" in all_specs:
                final_specs_for_update["description"] = all_specs["ai_description"]
            if "ai_features" in all_specs:
                final_specs_for_update["features"] = all_specs["ai_features"]

            # Log final state if AI extraction was attempted
            if ai_specs:
                logger.info("ℹ️ Combined specs ready for update for %s (Keys: %d)", product_name or url, len(final_specs_for_update))

            return final_specs_for_update

        except Exception as e:
            logger.error("❌ Error extracting specifications for %s: %s", product_name or url, e)
            return all_specs  # Return whatever was gathered, even if partial

    def _is_sufficiently_detailed(self, specs: Dict[str, Any]) -> bool:
        """Check if extracted structured data is detailed enough to potentially skip AI fallback.

        Criteria: Has a reasonable description and at least 3 other specific specification keys.
        """
        has_desc = bool(specs.get("description") and len(str(specs["description"])) > 50)
        # Count relevant spec keys using the defined exclusion list
        spec_keys = [k for k in specs.keys() if k not in _EXCLUDED_STRUCTURED_DATA_KEYS]
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
            # Extract metadata using extruct (supports JSON-LD, Microdata, OpenGraph)
            metadata = extruct.extract(html_content, base_url=base_url, uniform=True, syntaxes=["json-ld", "microdata", "opengraph"])

            specs = {}

            # Process JSON-LD data (highest priority)
            for item in metadata.get("json-ld", []):
                # Look for Product schema types
                if item.get("@type") == "Product" or item.get("@type") == "http://schema.org/Product":
                    # Extract common product properties
                    if "name" in item:
                        specs["name"] = item["name"]
                    if "brand" in item:
                        # Handle brand being an object or string
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
                    # Potentially add GTIN here too if needed: if "gtin" in item: specs["gtin"] = item["gtin"]

                    # Extract other properties as potential specifications
                    # Excluding common/already handled fields
                    excluded_keys = {"@context", "@type", "image", "url", "offers", "name", "brand", "description", "sku", "mpn", "model"}
                    for key, value in item.items():
                        if key not in excluded_keys:
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
                                # Map schema condition URL to simpler string if possible
                                condition_url = offer["itemCondition"]
                                if isinstance(condition_url, str):
                                    specs["condition"] = condition_url.split("/")[-1].lower()  # e.g., NewCondition -> new
                                else:
                                    specs["condition"] = str(condition_url)  # Fallback
                        elif isinstance(offer, list) and offer:
                            # If offers is a list, take the first one's details
                            first_offer = offer[0]
                            if isinstance(first_offer, dict):
                                if "price" in first_offer:
                                    specs["price"] = first_offer["price"]
                                if "availability" in first_offer:
                                    specs["availability"] = first_offer["availability"]
                                if "itemCondition" in first_offer:
                                    condition_url = first_offer["itemCondition"]
                                    if isinstance(condition_url, str):
                                        specs["condition"] = condition_url.split("/")[-1].lower()
                                    else:
                                        specs["condition"] = str(condition_url)

            # Process microdata (second priority, if JSON-LD wasn't sufficient)
            if len(specs) < 3:  # Check if we have minimal data before trying next format
                for item in metadata.get("microdata", []):
                    if item.get("type") in ["https://schema.org/Product", "http://schema.org/Product"]:
                        props = item.get("properties", {})
                        for key, value in props.items():
                            # If value is list, take first item, otherwise take value directly
                            if isinstance(value, list) and value:
                                specs[key] = value[0]
                            else:
                                specs[key] = value

            # Process OpenGraph data (third priority)
            if len(specs) < 3:
                og_data_list = metadata.get("opengraph", [])
                # Handle OpenGraph sometimes being a list of dicts
                if isinstance(og_data_list, list) and og_data_list:
                    self._extract_opengraph_dict(og_data_list[0], specs)
                # Handle OpenGraph potentially being a single dict (less common with extruct uniform=True)
                elif isinstance(og_data_list, dict):
                    self._extract_opengraph_dict(og_data_list, specs)

            return specs

        except Exception as e:
            logger.warning("⚠️ Error extracting structured data: %s", e)
            return {}

    def _extract_opengraph_dict(self, og_dict: dict, specs: dict) -> None:
        """Helper to extract relevant properties from an OpenGraph dictionary.

        Only adds data if the corresponding key doesn't already exist in specs.
        """
        # Access values safely with get() and only add if key is missing
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
        Clean and normalize text content extracted from HTML.

        Args:
            text: Raw text content

        Returns:
            Cleaned text string.
        """
        # Remove extra whitespace and normalize line breaks
        cleaned = re.sub(r"\s+", " ", text).strip()
        # Basic HTML entity decoding (can be expanded or use html.unescape)
        cleaned = cleaned.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        return cleaned

    async def _extract_specs_with_ai(self, html_content: str, product_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Use AI (OpenAI function calling or similar) to extract specifications from HTML
        when structured data isn't found or is insufficient.
        Uses JSON mode for more reliable structured output.

        Args:
            html_content: HTML content from product page
            product_name: Optional product name for context

        Returns:
            Dict[str, Any]: Extracted specifications as a dictionary, or empty dict on failure.
        """
        try:
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove common non-content elements aggressively using the defined selectors
            for selector in _NON_CONTENT_SELECTORS:
                for element in soup.select(selector):
                    if isinstance(element, Tag):
                        element.extract()

            # --- Targeted Content Extraction ---
            # Try to extract text from likely sections before falling back to broader content
            extracted_texts = []

            # Selectors for common product page sections (using constant)
            content_selectors = _CONTENT_SELECTORS

            processed_elements = set()  # Keep track of elements already processed

            # Extract from specific sections first
            for section_name, selectors in content_selectors.items():
                if section_name == "main_content":
                    continue  # Handle main content fallback later
                for selector in selectors:
                    elements = soup.select(selector)
                    for element in elements:
                        if isinstance(element, Tag) and element not in processed_elements:
                            section_text = element.get_text(separator="\n", strip=True)
                            if section_text:
                                # Prepend section name for AI context
                                extracted_texts.append(
                                    f"\n--- START {section_name.upper()} SECTION ---\n{section_text}\n--- END {section_name.upper()} SECTION ---\n"
                                )
                                processed_elements.add(element)
                            # Optionally remove the processed element to avoid duplication in fallback
                            # element.extract()

            # If few specific sections found, try main content area as a fallback
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
                # If targeted extraction yielded nothing, fallback to full body text (less reliable)
                logger.warning("⚠️ Could not extract targeted sections for %s, falling back to full body text.", product_name or "page")
                body = soup.find("body")
                final_text = body.get_text(separator="\n", strip=True) if body else ""

            # Further clean the combined text (remove excessive newlines)
            cleaned_text = re.sub(r"\n{3,}", "\n\n", final_text).strip()

            if not cleaned_text:
                logger.error("❌ No processable text content found after cleaning for %s", product_name or "page")
                return {}

            # Limit text length for API efficiency and cost saving
            max_len = 15000  # Adjust as needed based on model context window and cost
            if len(cleaned_text) > max_len:
                text_to_send = cleaned_text[:max_len] + "\n... (truncated due to length)"
                logger.warning("⚠️ Truncated targeted text content for AI extraction for %s (Sent %d chars)", product_name or "product", max_len)
            else:
                text_to_send = cleaned_text
                logger.info("ℹ️ Sending %d chars of targeted text to AI for %s", len(text_to_send), product_name or "product")

            # Create AI prompt for structured extraction using JSON mode
            context_str = f' for the product named "{product_name}"' if product_name else ""
            prompt = f"""Analyze the following text content extracted from specific sections of a product page{context_str}.
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
                use_json_mode=True,  # Enable JSON mode in OpenAI service
            )

            # Parse JSON response (should be more reliable with JSON mode)
            try:
                # Extract content from the response object
                content = response.choices[0].message.content if response.choices and response.choices[0].message.content else None
                if not content:
                    logger.error("❌ AI JSON mode response content is empty for %s.", product_name or "product")
                    return {}

                specs = json.loads(content)
                if not isinstance(specs, dict):
                    logger.error("❌ AI JSON mode response was not a dict for %s. Response: %s", product_name or "product", content[:500])
                    return {}

                # Basic validation of expected keys (optional but recommended)
                expected_keys = {"description", "specifications", "features", "brand", "category"}
                if not expected_keys.issubset(specs.keys()):
                    logger.warning("⚠️ AI JSON response missing expected keys for %s. Found: %s", product_name or "product", list(specs.keys()))
                    # Proceed anyway, but log the warning

                logger.info("✅ Successfully extracted data with AI (JSON Mode) for %s", product_name or "product")
                return specs

            except json.JSONDecodeError as e:
                # This should be rare with JSON mode, but handle defensively
                content = response.choices[0].message.content if response.choices and response.choices[0].message.content else "[Content Error]"
                logger.error("❌ Failed to parse AI JSON mode response for %s: %s\nResponse: %s", product_name or "product", e, content[:500])
                return {}

        except Exception as e:
            logger.error("❌ Error using AI to extract specifications for %s: %s", product_name or "product", e)
            return {}  # Return empty dict on failure
