from src.services.faiss_service import FAISSService
from src.services.openai_service import OpenAIService
from src.services.redis_service import RedisService
from src.utils.config import FAISS_VECTOR_DIMENSION, STORE_APIS


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
