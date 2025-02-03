from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router

# Initialize FastAPI app
app = FastAPI(
    title="AI-Powered Product Search API",
    description="An AI-driven product search system using OpenAI, FAISS, and live store data.",
    version="1.0.0",
)

# Allow frontend apps to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all domains (change this in production!)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include all API routes
app.include_router(router)


@app.get("/")
def health_check():
    """
    Health check endpoint to verify if the API is running.
    """
    return {"message": "🚀 Product Search API is running!"}
