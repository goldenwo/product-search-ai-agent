import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Debug Mode
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# FAISS Vector Dimension
FAISS_VECTOR_DIMENSION = int(os.getenv("FAISS_VECTOR_DIMENSION", "128"))

# API Endpoints (Dynamic Configurations)
STORE_APIS = {
    "Amazon": os.getenv("AMAZON_API_URL", "https://api.amazon.com/search"),
    "Best Buy": os.getenv("BESTBUY_API_URL", "https://api.bestbuy.com/v1/products"),
}

# Print Config (Optional: for Debugging)
if DEBUG:
    print(f"Loaded Config: OPENAI_API_KEY={OPENAI_API_KEY[:5]}****, DEBUG={DEBUG}")
