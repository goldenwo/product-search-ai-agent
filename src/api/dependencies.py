from src.utils.config import STORE_APIS, FAISS_VECTOR_DIMENSION
from src.services.openai_service import OpenAIService
from src.services.faiss_service import FAISSService
from src.services.redis_service import RedisService

# FAISS Vector Search Dependency
def get_faiss():
    return FAISSService(vector_dimension=FAISS_VECTOR_DIMENSION)

# OpenAI API Dependency
def get_openai_service():
    return OpenAIService()

# Store API URLs Dependency
def get_store_apis():
    return STORE_APIS

# Redis Dependency
def get_redis():
    return RedisService()
