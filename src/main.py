"""Main module for the AI-Powered Product Search API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import auth, routes

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

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(routes.router, prefix="/api", tags=["search"])
