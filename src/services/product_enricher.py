"""Service for enriching products with detailed specifications."""

import json
import re
from typing import Any, Dict, List, Optional

import aiohttp
import extruct
from bs4 import BeautifulSoup, Tag
from w3lib.html import get_base_url

from src.models.product import Product
from src.services.openai_service import OpenAIService
from src.utils import logger


class ProductEnricher:
    """
    Service for enriching products with detailed specifications.

    Methods:
    - Fetch additional information from product pages
    - Extract specifications from HTML
    - Normalize and structure product data

    Attributes:
        openai_service: OpenAI service for extracting structured data
    """

    def __init__(self):
        """Initialize the product enricher service."""
        self.openai_service = OpenAIService()

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
            logger.error("❌ Error enriching product: %s", str(e))
            return product

    def _update_product_from_specs(self, product: Product, specs: Dict[str, Any]) -> Product:
        """
        Update a Product object with extracted specifications.

        Args:
            product: Original Product object
            specs: Extracted specifications

        Returns:
            Product: Updated Product object
        """
        # Create a dict representation of the product
        product_dict = product.model_dump()

        # Map common specification fields to product attributes
        field_mappings = {
            "brand": "brand",
            "description": "description",
            "category": "category",
            "sku": "id",  # Only update if original ID is generic
            "mpn": None,  # Store in specifications
            "model": None,  # Store in specifications
            "price": None,  # Don't override original price
            "availability": None,  # Store in specifications
            "condition": None,  # Store in specifications
            "rating": "rating",
            "reviewCount": "review_count",
        }

        # Update mapped fields if they exist in specs and are empty in product
        for spec_key, product_field in field_mappings.items():
            if spec_key in specs and specs[spec_key]:
                if product_field and (product_dict.get(product_field) is None or product_dict.get(product_field) == ""):
                    product_dict[product_field] = specs[spec_key]

        # Save all specifications to specifications field
        if product.specifications is None:
            product_dict["specifications"] = {}

        # Only keep relevant specification fields
        filtered_specs = {k: v for k, v in specs.items() if k not in ["product_id", "name"] and v}

        # Merge with existing specifications
        product_dict["specifications"] = {**filtered_specs, **(product_dict["specifications"] or {})}

        # Create updated product
        return Product.model_validate(product_dict)

    async def _fetch_product_page(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from product page.

        Args:
            url: Product page URL

        Returns:
            Optional[str]: HTML content or None if failed
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.warning("⚠️ Failed to fetch page, status: %d", response.status)
                        return None

                    return await response.text()

        except aiohttp.ClientError as e:
            logger.error("❌ HTTP error fetching product page: %s", str(e))
            return None
        except Exception as e:
            logger.error("❌ Unexpected error fetching product page: %s", str(e))
            return None

    async def _extract_specifications(self, html_content: str, url: str, product_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract product specifications from HTML content.

        Args:
            html_content: HTML content from product page
            url: URL of the product page for base URL resolution
            product_name: Optional product name for context

        Returns:
            Dict[str, Any]: Extracted product specifications
        """
        try:
            # 1. First try using extruct to get structured metadata
            structured_data = self._extract_structured_data(html_content, url)
            if structured_data and len(structured_data) >= 3:
                logger.info("✅ Successfully extracted specifications using structured data")
                return structured_data

            # 2. Fall back to HTML parsing
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract potential specification sections
            spec_sections = self._find_specification_sections(soup)

            if not spec_sections:
                # If no structured specs found, try AI extraction from page content
                return await self._extract_specs_with_ai(html_content, product_name)

            # Extract specifications from sections
            specs = {}
            for section in spec_sections:
                section_specs = self._parse_specification_section(section)
                specs.update(section_specs)

            # If too few specs were found, try AI extraction as well
            if len(specs) < 3:
                ai_specs = await self._extract_specs_with_ai(html_content, product_name)
                # Merge the specs, prioritizing the ones extracted from HTML
                merged_specs = {**ai_specs, **specs}
                return merged_specs

            return specs

        except Exception as e:
            logger.error("❌ Error extracting specifications: %s", str(e))
            return {}

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

    def _find_specification_sections(self, soup: BeautifulSoup) -> List[Tag]:
        """
        Find sections in HTML that likely contain product specifications.

        Args:
            soup: BeautifulSoup object of the HTML

        Returns:
            List[Tag]: List of HTML elements containing specifications
        """
        # Common patterns for specification sections
        spec_sections = []

        # Look for tables with specification-like content
        for table in soup.find_all("table"):
            if isinstance(table, Tag) and self._looks_like_spec_table(table):
                spec_sections.append(table)

        # Look for div sections with specification-like class names
        for div in soup.find_all("div"):
            if not isinstance(div, Tag):
                continue
            class_attr = div.get("class")
            if class_attr and any(term in " ".join(class_attr).lower() for term in ["spec", "detail", "feature", "info", "attribute"]):
                spec_sections.append(div)

        # Look for lists that might contain specifications
        for tag in soup.find_all(["ul", "ol"]):
            if not isinstance(tag, Tag):
                continue
            class_attr = tag.get("class")
            if class_attr and any(term in " ".join(class_attr).lower() for term in ["spec", "detail", "feature", "info", "attribute"]):
                spec_sections.append(tag)

        # Look for sections with specification-like IDs
        for id_term in ["specs", "specifications", "details", "features", "product-info"]:
            spec_element = soup.find(id=id_term)
            if spec_element and isinstance(spec_element, Tag):
                spec_sections.append(spec_element)

            # Also try with data attributes
            elements = soup.find_all(attrs={"data-id": id_term})
            for element in elements:
                if isinstance(element, Tag):
                    spec_sections.append(element)

        return spec_sections

    def _looks_like_spec_table(self, table: Tag) -> bool:
        """
        Check if a table appears to contain specifications.

        Args:
            table: HTML table element

        Returns:
            bool: True if table likely contains specifications
        """
        # Check if the element is a table tag
        if not isinstance(table, Tag) or table.name != "table":
            return False

        # Find rows in the table
        rows = []
        for row in table.find_all("tr"):
            if isinstance(row, Tag):
                rows.append(row)

        if len(rows) < 2:
            return False

        # Check if rows have a key-value structure (2 cells)
        two_column_rows = []
        for row in rows:
            cells = []
            for cell in row.find_all(["td", "th"]):
                if isinstance(cell, Tag):
                    cells.append(cell)
            if len(cells) == 2:
                two_column_rows.append(row)

        return len(two_column_rows) > len(rows) / 2

    def _parse_specification_section(self, section: Tag) -> Dict[str, str]:
        """
        Parse a specification section into key-value pairs.

        Args:
            section: HTML element containing specifications

        Returns:
            Dict[str, str]: Extracted specifications
        """
        specs = {}

        # Handle tables
        if section.name == "table":
            for row in section.find_all("tr"):
                if not isinstance(row, Tag):
                    continue

                cells = []
                for cell in row.find_all(["td", "th"]):
                    if isinstance(cell, Tag):
                        cells.append(cell)

                if len(cells) >= 2:
                    key = self._clean_text(cells[0].get_text())
                    value = self._clean_text(cells[1].get_text())
                    if key and value:
                        specs[key] = value

        # Handle lists
        elif section.name in ["ul", "ol"]:
            for item in section.find_all("li"):
                if not isinstance(item, Tag):
                    continue

                text = self._clean_text(item.get_text())
                # Try to split into key-value pair
                if ":" in text:
                    key, value = text.split(":", 1)
                    if key and value:
                        specs[key.strip()] = value.strip()

        # Handle divs (more complex)
        elif section.name == "div":
            # Look for structured data within the div
            dt_elements = []
            dd_elements = []

            for dt in section.find_all("dt"):
                if isinstance(dt, Tag):
                    dt_elements.append(dt)

            for dd in section.find_all("dd"):
                if isinstance(dd, Tag):
                    dd_elements.append(dd)

            if len(dt_elements) > 0 and len(dt_elements) == len(dd_elements):
                for dt, dd in zip(dt_elements, dd_elements):
                    key = self._clean_text(dt.get_text())
                    value = self._clean_text(dd.get_text())
                    if key and value:
                        specs[key] = value

            # Try other patterns in divs
            else:
                # Look for labeled paragraphs
                for p in section.find_all("p"):
                    if not isinstance(p, Tag):
                        continue

                    text = self._clean_text(p.get_text())
                    if ":" in text:
                        key, value = text.split(":", 1)
                        if key and value:
                            specs[key.strip()] = value.strip()

                # Also check for span elements with key-value pairs
                try:
                    for span in section.find_all("span"):
                        if not isinstance(span, Tag):
                            continue

                        # Check if this span has a class containing "label"
                        class_attr = span.get("class")
                        is_label = False
                        if class_attr:
                            is_label = any("label" in cls.lower() for cls in class_attr if isinstance(cls, str))

                        if is_label:
                            key = self._clean_text(span.get_text())
                            # Try to find corresponding value span (usually a sibling)
                            value_span = span.find_next_sibling("span")
                            if value_span and isinstance(value_span, Tag):
                                value = self._clean_text(value_span.get_text())
                                if key and value:
                                    specs[key] = value
                except Exception as e:
                    logger.warning("⚠️ Error parsing span elements: %s", str(e))

        return specs

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize text content.

        Args:
            text: Raw text content

        Returns:
            str: Cleaned text
        """
        # Remove extra whitespace
        cleaned = re.sub(r"\s+", " ", text).strip()
        # Remove common filler words
        cleaned = re.sub(r"^(Specifications:|Details:|Features:)\s*", "", cleaned)
        return cleaned

    async def _extract_specs_with_ai(self, html_content: str, product_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Use AI to extract specifications from HTML when structured data isn't found.

        Args:
            html_content: HTML content from product page
            product_name: Optional product name for context

        Returns:
            Dict[str, Any]: Extracted specifications
        """
        # Extract text content from HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove scripts, styles, and hidden elements
        for selector in ["script", "style", "head", "title", "meta", "[document]"]:
            for element in soup.select(selector):
                if isinstance(element, Tag):
                    element.extract()

        # Get visible text
        text = soup.get_text(separator=" ", strip=True)

        # Limit text length for API
        text = text[:8000]  # Limit to avoid token limits

        # Create AI prompt
        context = f" for the product named {product_name}" if product_name else ""
        prompt = f"""Extract the technical specifications{context} from this product page content. 
Return the specifications as a JSON object where keys are specification names and values are 
the specification values. Focus on important technical details.

Page content:
{text}

Return ONLY a valid JSON object containing the specifications without any additional text or explanation.
Example:
{{
  "Display": "6.7 inch OLED",
  "Processor": "A15 Bionic",
  "Storage": "128GB"
}}
"""

        try:
            # Get AI response
            response = self.openai_service.generate_response(prompt)

            # Parse JSON from response
            try:
                # Clean the response to ensure it's valid JSON
                response = response.strip()
                if response.startswith("```json"):
                    response = response[7:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()

                specs = json.loads(response)
                logger.info("✅ Successfully extracted %d specifications with AI", len(specs))
                return specs

            except json.JSONDecodeError as e:
                logger.error("❌ Failed to parse AI response as JSON: %s", str(e))
                return {}

        except Exception as e:
            logger.error("❌ Error using AI to extract specifications: %s", str(e))
            return {}
