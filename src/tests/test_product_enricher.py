# src/tests/test_product_enricher.py

from decimal import Decimal
import json
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import HttpUrl
import pytest

from src.models.product import Product
from src.services.openai_service import OpenAIService, OpenAIServiceError
from src.services.product_enricher import ProductEnricher

# Sample HTML snippets for testing parsing
SAMPLE_HTML_NO_STRUCTURED_DATA = """
<html><body><h1>Product Title</h1><div class=\"description\"><p>This is the description.</p></div></body></html>
"""

SAMPLE_HTML_JSON_LD = """
<html>
<head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "Test Product JSON-LD",
      "description": "Description from JSON-LD.",
      "brand": {"@type": "Brand", "name": "JSON-LD Brand"},
      "sku": "SKU123",
      "offers": {
        "@type": "Offer",
        "price": "19.99",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock"
      },
      "aggregateRating": {
        "@type": "AggregateRating",
        "ratingValue": "4.5",
        "reviewCount": "100"
      }
    }
    </script>
</head>
<body><h1>Product Title</h1></body>
</html>
"""

SAMPLE_HTML_MICRODATA = """
<html>
<body itemscope itemtype=\"http://schema.org/Product\">
    <h1 itemprop=\"name\">Test Product Microdata</h1>
    <div itemprop=\"brand\" itemscope itemtype=\"http://schema.org/Brand\">
        <span itemprop=\"name\">Microdata Brand</span>
    </div>
    <p itemprop=\"description\">Description from Microdata.</p>
    <div itemprop=\"offers\" itemscope itemtype=\"http://schema.org/Offer\">
        <span itemprop=\"price\">25.50</span>
        <meta itemprop=\"priceCurrency\" content=\"USD\" />
        <link itemprop=\"availability\" href=\"http://schema.org/InStock\"/>
    </div>
    <span itemprop=\"sku\">SKU456</span>
</body>
</html>
"""

SAMPLE_HTML_OPENGRAΡH = """
<html>
<head>
    <meta property=\"og:title\" content=\"Test Product OpenGraph\" />
    <meta property=\"og:description\" content=\"Description from OpenGraph.\" />
    <meta property=\"og:price:amount\" content=\"30.00\" />
    <meta property=\"og:price:currency\" content=\"EUR\" />
    <meta property=\"og:brand\" content=\"OpenGraph Brand\" />
</head>
<body><h1>Product Title</h1></body>
</html>
"""

SAMPLE_HTML_FOR_AI = """
<html>
<head><title>AI Test Product</title></head>
<body>
    <header>Nav stuff</header>
    <main id=\"main\">
        <h1>AI Test Product</h1>
        <div class=\"brand-info\">Brand: AI Brand</div>
        <section id=\"productDescription\">
            <h2>Description</h2>
            <p>This is the main description text. It has several features.</p>
        </section>
        <section class=\"product-features\">
            <h2>Features</h2>
            <ul><li>Feature 1</li><li>Feature 2</li><li>Long Feature 3 explains benefits</li></ul>
        </section>
        <section id=\"technicalSpecifications_feature_div\">
            <h2>Specifications</h2>
            <table>
                <tr><td>Screen Size</td><td>15 inch</td></tr>
                <tr><td>RAM</td><td>8GB DDR4</td></tr>
                <tr><td>Storage</td><td>256GB SSD</td></tr>
            </table>
        </section>
        <div class=\"related-products\">Related items</div>
    </main>
    <footer>Footer info</footer>
    <script>alert('hello');</script>
</body>
</html>
"""


@pytest.fixture
def mock_openai_service():
    """Provides a MagicMock for the OpenAIService."""
    service = MagicMock(spec=OpenAIService)
    # Default mock response for successful AI extraction
    mock_ai_choice = MagicMock()
    mock_ai_choice.message.content = """
    {
        "description": "AI extracted description.",
        "specifications": { "Color": "Blue", "Weight": "1kg" },
        "features": ["AI Feature 1", "AI Feature 2"],
        "brand": "AI Brand",
        "category": "AI Category"
    }
    """
    mock_ai_completion = MagicMock()
    mock_ai_completion.choices = [mock_ai_choice]
    mock_ai_completion.usage.prompt_tokens = 50
    mock_ai_completion.usage.completion_tokens = 50
    mock_ai_completion.usage.total_tokens = 100
    # The method being mocked is async, so we must use AsyncMock
    service.generate_response = AsyncMock(return_value=mock_ai_completion)
    return service


@pytest.fixture
def product_enricher(mock_openai_service):
    """Provides a ProductEnricher instance with a mocked OpenAIService."""
    return ProductEnricher(openai_service=mock_openai_service)


# --- Tests for internal helpers (_update_product_from_specs) ---


def test_update_product_from_specs_empty_product():
    """Test updating an empty product with new specs."""
    enricher = ProductEnricher(openai_service=MagicMock())
    product = Product(id="p1", title="Test", price=Decimal("10.00"), store="store", url=HttpUrl("http://example.com"))
    specs = {
        "brand": "New Brand",
        "description": "New Description",
        "category": "New Category",
        "rating": 4.0,
        "reviewCount": 50,
        "specifications": {"Size": "Large"},
        "features": ["Feature A"],
    }
    updated_product = enricher._update_product_from_specs(product, specs)

    assert updated_product.brand == "New Brand"
    assert updated_product.description == "New Description"
    assert updated_product.category == "New Category"
    assert updated_product.rating == 4.0
    assert updated_product.review_count == 50
    assert updated_product.specifications["Size"] == "Large"
    assert updated_product.specifications["Features"] == "Feature A"


def test_update_product_from_specs_no_overwrite():
    """Test that existing valid data isn't overwritten."""
    enricher = ProductEnricher(openai_service=MagicMock())
    product = Product(
        id="p1",
        title="Test",
        price=Decimal("10.00"),
        store="store",
        url=HttpUrl("http://example.com"),
        brand="Old Brand",
        description="Old Description that is sufficiently long for testing purposes.",
        category="Old Category",
        rating=3.0,
        review_count=20,
        specifications={"Color": "Red", "Features": "Old Feature"},
    )
    specs = {
        "brand": "New Brand",
        "description": "Shorter new desc.",  # Should not overwrite longer old one
        "category": "New Category",
        "rating": 4.0,
        "reviewCount": 50,
        "specifications": {"Size": "Large", "Color": "Blue"},  # Color shouldn't overwrite
        "features": ["Feature A"],  # Features list shouldn't overwrite existing 'Features' spec
    }
    updated_product = enricher._update_product_from_specs(product, specs)

    assert updated_product.brand == "Old Brand"
    assert updated_product.description == "Old Description that is sufficiently long for testing purposes."
    assert updated_product.category == "Old Category"
    assert updated_product.rating == 3.0
    assert updated_product.review_count == 20
    assert updated_product.specifications["Color"] == "Red"
    assert updated_product.specifications["Size"] == "Large"  # New spec added
    assert updated_product.specifications["Features"] == "Old Feature"  # Not overwritten by list


def test_update_product_from_specs_merge_specs():
    """Test merging of specification dictionaries."""
    enricher = ProductEnricher(openai_service=MagicMock())
    product = Product(
        id="p1", title="Test", price=Decimal("10.00"), store="store", url=HttpUrl("http://example.com"), specifications={"Color": "Red"}
    )
    specs = {
        "specifications": {"Size": "Large", "Material": "Cotton"},
    }
    updated_product = enricher._update_product_from_specs(product, specs)

    assert updated_product.specifications == {"Color": "Red", "Size": "Large", "Material": "Cotton"}


def test_update_product_from_specs_add_features_list():
    """Test adding features from a list when 'Features' spec doesn't exist."""
    enricher = ProductEnricher(openai_service=MagicMock())
    product = Product(
        id="p1", title="Test", price=Decimal("10.00"), store="store", url=HttpUrl("http://example.com"), specifications={"Color": "Red"}
    )
    specs = {"features": ["Feature A", "Feature B", " "]}  # Includes empty feature
    updated_product = enricher._update_product_from_specs(product, specs)

    assert updated_product.specifications["Features"] == "Feature A, Feature B"
    assert updated_product.specifications["Color"] == "Red"


# --- Tests for _extract_structured_data ---


def test_extract_structured_data_json_ld(product_enricher):
    """Test extracting data primarily from JSON-LD."""
    specs = product_enricher._extract_structured_data(SAMPLE_HTML_JSON_LD, "http://example.com")
    assert specs["name"] == "Test Product JSON-LD"
    assert specs["description"] == "Description from JSON-LD."
    assert specs["brand"] == "JSON-LD Brand"
    assert specs["sku"] == "SKU123"
    assert specs["price"] == "19.99"
    assert specs["availability"] == "https://schema.org/InStock"
    # Check aggregateRating is extracted as a nested dict (not flattened automatically)
    assert isinstance(specs.get("aggregateRating"), dict)
    assert specs["aggregateRating"]["ratingValue"] == "4.5"
    assert specs["aggregateRating"]["reviewCount"] == "100"


def test_extract_structured_data_microdata(product_enricher):
    """Test extracting data from Microdata."""
    specs = product_enricher._extract_structured_data(SAMPLE_HTML_MICRODATA, "http://example.com")
    assert specs.get("name") == "Test Product Microdata"
    assert specs.get("brand") == "Microdata Brand"
    assert specs.get("description") == "Description from Microdata."
    assert specs.get("sku") == "SKU456"
    assert specs.get("price") == "25.50"
    assert specs.get("availability") == "http://schema.org/InStock"


def test_extract_structured_data_opengraph(product_enricher):
    """Test extracting data from OpenGraph meta tags."""
    specs = product_enricher._extract_structured_data(SAMPLE_HTML_OPENGRAΡH, "http://example.com")
    assert specs["name"] == "Test Product OpenGraph"
    assert specs["description"] == "Description from OpenGraph."
    assert specs["brand"] == "OpenGraph Brand"
    assert specs["price"] == "30.00"
    assert specs["currency"] == "EUR"


def test_extract_structured_data_none(product_enricher):
    """Test handling HTML with no structured data."""
    specs = product_enricher._extract_structured_data(SAMPLE_HTML_NO_STRUCTURED_DATA, "http://example.com")
    assert specs == {}


# --- Tests for _fetch_product_page (More involved mocking needed) ---


@pytest.mark.asyncio
# Patch the 'get' method within the ClientSession class
@patch("aiohttp.ClientSession.get")
async def test_fetch_product_page_standard_success(mock_get, product_enricher):
    """Test successful standard HTTP fetch using simplified patching."""
    # 1. Configure the mock response object
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=SAMPLE_HTML_JSON_LD)
    mock_response.get_encoding.return_value = "utf-8"

    # 2. Configure the mock_get's return_value (the async context manager)
    #    Its __aenter__ should return the mock_response
    mock_async_context_manager = AsyncMock()
    mock_async_context_manager.__aenter__.return_value = mock_response
    mock_get.return_value = mock_async_context_manager

    # 3. Call the function under test
    html = await product_enricher._fetch_product_page("http://example.com/success")

    # 4. Assertions
    assert html == SAMPLE_HTML_JSON_LD
    # Check that session.get was called
    mock_get.assert_called_once()
    # Check that response.text() was awaited
    mock_response.text.assert_awaited_once()


@pytest.mark.asyncio
# Patch 'get' for this test too
@patch("aiohttp.ClientSession.get")
@patch("src.services.product_enricher.ENRICHMENT_USE_HEADLESS_FALLBACK", False)
async def test_fetch_product_page_standard_fail_no_fallback(mock_get, product_enricher):
    """Test standard fetch failure when fallback is disabled."""
    mock_response = AsyncMock()
    mock_response.status = 404
    # Configure the context manager mock for failure case
    mock_async_context_manager = AsyncMock()
    mock_async_context_manager.__aenter__.return_value = mock_response
    mock_get.return_value = mock_async_context_manager

    html = await product_enricher._fetch_product_page("http://example.com/fail")
    assert html is None
    mock_get.assert_called_once()


@pytest.mark.asyncio
@patch("aiohttp.ClientSession.get")
@patch("src.services.product_enricher.async_playwright")
@patch("src.services.product_enricher.ENRICHMENT_USE_HEADLESS_FALLBACK", True)
async def test_fetch_product_page_standard_fail_fallback_success(mock_playwright, mock_get, product_enricher):
    """Test standard fetch failure triggering successful Playwright fallback."""
    # Simulate standard fetch failure (aiohttp)
    mock_response_http = AsyncMock()
    mock_response_http.status = 500
    mock_async_context_manager = AsyncMock()
    mock_async_context_manager.__aenter__.return_value = mock_response_http
    mock_get.return_value = mock_async_context_manager

    # ---- Configure the entire Playwright mock chain ----
    # 1. Mock the page object and its methods/properties
    mock_page = AsyncMock(name="FinalMockPage")
    mock_page.goto = AsyncMock()  # Make goto awaitable
    # Ensure .content() itself is awaitable and returns the desired string
    mock_page.content = AsyncMock(return_value="<html><body>Playwright Content</body></html>")

    # 2. Mock the browser object and its methods
    mock_browser = AsyncMock(name="FinalMockBrowser")
    mock_browser.new_page = AsyncMock(return_value=mock_page)  # Make new_page awaitable
    mock_browser.close = AsyncMock()  # Make close awaitable

    # 3. Mock the playwright context object (p) and its methods
    mock_pw_context = AsyncMock(name="FinalMockPwContext")
    # Ensure chromium.launch is awaitable and returns the mock_browser
    # We need to mock the chromium attribute first
    mock_pw_context.chromium = AsyncMock()
    mock_pw_context.chromium.launch = AsyncMock(return_value=mock_browser)

    # 4. Configure the top-level mock_playwright context manager
    #    Its __aenter__ should return the mock_pw_context
    mock_playwright.return_value.__aenter__.return_value = mock_pw_context
    # Ensure __aexit__ is also an AsyncMock if it's awaited implicitly
    mock_playwright.return_value.__aexit__ = AsyncMock()

    # ---- Call the function under test ----
    html = await product_enricher._fetch_product_page("http://example.com/fallback_success")

    # ---- Assertions ----
    assert html == "<html><body>Playwright Content</body></html>"

    # Verify the chain of calls
    mock_get.assert_called_once()  # aiohttp called
    mock_playwright.assert_called_once()  # playwright context manager used
    mock_playwright.return_value.__aenter__.assert_awaited_once()  # Entered context
    mock_pw_context.chromium.launch.assert_awaited_once()  # Browser launched
    mock_browser.new_page.assert_awaited_once()  # Page created
    mock_page.goto.assert_awaited_once()  # Navigation attempted
    mock_page.content.assert_awaited_once()  # Content retrieved
    mock_browser.close.assert_awaited_once()  # Browser closed
    mock_playwright.return_value.__aexit__.assert_awaited_once()  # Exited context


@pytest.mark.asyncio
@patch("aiohttp.ClientSession.get")
@patch("src.services.product_enricher.async_playwright")
@patch("src.services.product_enricher.ENRICHMENT_USE_HEADLESS_FALLBACK", True)
async def test_fetch_product_page_standard_fail_fallback_fail(mock_playwright, mock_get, product_enricher):
    """Test standard fetch failure triggering failed Playwright fallback."""
    # Simulate standard fetch failure
    mock_response_http = AsyncMock()
    mock_response_http.status = 500
    mock_async_context_manager = AsyncMock()
    mock_async_context_manager.__aenter__.return_value = mock_response_http
    mock_get.return_value = mock_async_context_manager

    # Simulate Playwright failure with explicit async mocks
    mock_page = AsyncMock(name="TestMockPageFail")
    mock_page.goto = AsyncMock()
    mock_page.content = AsyncMock(return_value="This should not be returned")

    mock_browser = AsyncMock(name="TestMockBrowserFail")
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()  # Should still be an AsyncMock

    mock_pw_context = AsyncMock(name="TestMockPwContextFail")
    # We need to mock the chromium attribute first
    mock_pw_context.chromium = AsyncMock()
    # Make launch awaitable but raise exception
    mock_pw_context.chromium.launch = AsyncMock(side_effect=Exception("Playwright launch failed"))

    mock_playwright.return_value.__aenter__.return_value = mock_pw_context
    # Mock __aexit__ too, as it might be called during exception handling
    mock_playwright.return_value.__aexit__ = AsyncMock()

    html = await product_enricher._fetch_product_page("http://example.com/fallback_fail")
    assert html is None
    mock_get.assert_called_once()
    mock_playwright.assert_called_once()
    mock_pw_context.chromium.launch.assert_awaited_once()


# --- Tests for _extract_specs_with_ai ---


@pytest.mark.asyncio
async def test_extract_specs_with_ai_success(product_enricher, mock_openai_service):
    """Test successful AI extraction."""
    # The fixture is now correctly configured, so no need for a local override.
    specs = await product_enricher._extract_specs_with_ai(SAMPLE_HTML_FOR_AI, "AI Test Product")

    assert specs["brand"] == "AI Brand"
    assert specs["category"] == "AI Category"
    assert specs["description"] == "AI extracted description."
    assert specs["features"] == ["AI Feature 1", "AI Feature 2"]
    assert specs["specifications"] == {"Color": "Blue", "Weight": "1kg"}
    mock_openai_service.generate_response.assert_called_once()
    # Optionally, assert parts of the prompt sent to the AI
    prompt_arg = mock_openai_service.generate_response.call_args[0][0]
    assert "AI Test Product" in prompt_arg
    assert "--- START DESCRIPTION SECTION ---" in prompt_arg
    assert "--- START FEATURES SECTION ---" in prompt_arg
    assert "--- START SPECIFICATIONS SECTION ---" in prompt_arg
    # Check that cleaned text was sent (header/footer/script removed)
    assert "<header>" not in prompt_arg
    assert "<footer>" not in prompt_arg
    assert "<script>" not in prompt_arg


@pytest.mark.asyncio
async def test_extract_specs_with_ai_error(product_enricher, mock_openai_service):
    """Test AI extraction when OpenAI service fails."""
    mock_openai_service.generate_response.side_effect = OpenAIServiceError("AI failed")

    specs = await product_enricher._extract_specs_with_ai(SAMPLE_HTML_FOR_AI, "AI Test Product")

    assert specs == {}  # Should return empty dict on failure
    mock_openai_service.generate_response.assert_called_once()


@pytest.mark.asyncio
async def test_extract_specs_with_ai_bad_json(product_enricher, mock_openai_service):
    """Test AI extraction when AI returns invalid JSON."""
    mock_ai_choice = MagicMock()
    mock_ai_choice.message.content = "This is not JSON { definitely not"
    mock_ai_completion = MagicMock()
    mock_ai_completion.choices = [mock_ai_choice]
    # The generate_response mock is an AsyncMock from the fixture; we can update its return_value for this test.
    mock_openai_service.generate_response.return_value = mock_ai_completion

    specs = await product_enricher._extract_specs_with_ai(SAMPLE_HTML_FOR_AI, "AI Test Product")

    assert specs == {}  # Should return empty dict on JSON parse failure
    mock_openai_service.generate_response.assert_called_once()


# --- Tests for _extract_specifications (Orchestration) ---


@pytest.mark.asyncio
async def test_extract_specifications_structured_sufficient(product_enricher, mock_openai_service):
    """Test extraction stops when structured data is deemed sufficient."""
    # Mock _extract_structured_data to return 'sufficient' data
    sufficient_data = {
        "name": "Sufficient Product",
        "description": "This description is definitely long enough to be considered sufficient for testing.",
        "brand": "Sufficient Brand",
        "sku": "SKU_SUFF",
        "color": "Green",
        "material": "Wood",
    }
    with patch.object(product_enricher, "_extract_structured_data", return_value=sufficient_data):
        # Mock _is_sufficiently_detailed (though the logic above should make it sufficient)
        with patch.object(product_enricher, "_is_sufficiently_detailed", return_value=True):
            specs = await product_enricher._extract_specifications(SAMPLE_HTML_JSON_LD, "http://example.com", "Sufficient Product")

    assert specs == sufficient_data  # Should return the structured data
    mock_openai_service.generate_response.assert_not_called()  # AI should not be called


@pytest.mark.asyncio
async def test_extract_specifications_structured_insufficient_ai_fallback(product_enricher, mock_openai_service):
    """Test AI fallback when structured data is insufficient."""
    # Mock _extract_structured_data to return 'insufficient' data
    insufficient_data = {
        "name": "Insufficient Product",
        "price": "10.00",  # Missing description and enough other keys
    }
    # AI mock will return its standard data (brand: AI Brand, category: AI Category etc.)
    ai_data_from_mock = json.loads(mock_openai_service.generate_response.return_value.choices[0].message.content)

    with patch.object(product_enricher, "_extract_structured_data", return_value=insufficient_data):
        # Ensure sufficiency check returns False
        with patch.object(product_enricher, "_is_sufficiently_detailed", return_value=False):
            # Mock the AI extraction part to ensure it's called
            with patch.object(product_enricher, "_extract_specs_with_ai", return_value=ai_data_from_mock) as mock_ai_extract:
                specs = await product_enricher._extract_specifications(SAMPLE_HTML_FOR_AI, "http://example.com", "Insufficient Product")

    # Assertions:
    mock_ai_extract.assert_called_once()  # Verify AI extraction was called
    # Check that the final result merges insufficient structured data and AI data
    # The _update_product logic isn't run here, just the merge in _extract_specifications
    assert specs["name"] == "Insufficient Product"  # From structured data
    assert specs["price"] == "10.00"  # From structured data
    assert specs["brand"] == "AI Brand"  # From AI
    assert specs["category"] == "AI Category"  # From AI
    assert specs["description"] == "AI extracted description."  # From AI
    assert specs["features"] == ["AI Feature 1", "AI Feature 2"]  # From AI
    assert specs["specifications"] == {"Color": "Blue", "Weight": "1kg"}  # From AI


# --- Tests for enrich_product (Orchestration) ---


@pytest.mark.asyncio
async def test_enrich_product_success(product_enricher):
    """Test the main enrich_product orchestrator method."""
    product = Product(id="p1", title="Test Enrich", price=Decimal("10.00"), store="store", url=HttpUrl("http://example.com/enrich"))
    expected_specs = {
        "brand": "Fetched Brand",
        "description": "Fetched Description",
        "category": "Fetched Category",
        "specifications": {"Material": "Metal"},
    }

    # Mock get_product_specs to return some data
    with patch.object(product_enricher, "get_product_specs", return_value=expected_specs) as mock_get_specs:
        enriched = await product_enricher.enrich_product(product)

    mock_get_specs.assert_called_once_with(product_id=product.id, product_url=str(product.url), name=product.title)
    # Check that the product was updated based on the mocked specs
    assert enriched.brand == "Fetched Brand"
    assert enriched.description == "Fetched Description"
    assert enriched.category == "Fetched Category"
    assert enriched.specifications["Material"] == "Metal"


@pytest.mark.asyncio
async def test_enrich_product_fetch_fails(product_enricher, caplog):
    """Test enrich_product when get_product_specs returns nothing."""
    product = Product(id="p1", title="Fetch Fail Product", price=Decimal("10.00"), store="store", url=HttpUrl("http://example.com/fetchfail"))

    # Mock get_product_specs to return empty dict
    with patch.object(product_enricher, "get_product_specs", return_value={}) as mock_get_specs:
        enriched = await product_enricher.enrich_product(product)

    assert enriched is product  # Should return original product
    mock_get_specs.assert_called_once()
    assert "No specifications found for product" in caplog.text
