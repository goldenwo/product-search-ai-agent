import os

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Debug mode (default: False)
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# FAISS Vector Search Configuration
FAISS_VECTOR_DIMENSION = int(os.getenv("FAISS_VECTOR_DIMENSION", "128"))

# Store API URLs
STORE_APIS = {
    "Amazon": os.getenv("AMAZON_API_URL", "https://api.amazon.com/search"),
    "BestBuy": os.getenv("BESTBUY_API_URL", "https://api.bestbuy.com/v1/products"),
    "eBay": os.getenv("EBAY_API_URL", "https://api.ebay.com/find"),
}

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_TTL = int(os.getenv("REDIS_TTL", 300))  # Cache timeout (default: 300 seconds)

# Print config (Debug Mode Only)
if DEBUG:
    print(f"✅ Loaded Config: FAISS_VECTOR_DIMENSION={FAISS_VECTOR_DIMENSION}, DEBUG={DEBUG}")
    print(f"✅ Redis Config: {REDIS_HOST}:{REDIS_PORT}, DB={REDIS_DB}, TTL={REDIS_TTL}")
