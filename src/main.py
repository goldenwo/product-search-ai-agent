"""Main module for the AI-Powered Product Search API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api import auth, routes
from src.dependencies import limiter
from src.middleware import AuthMiddleware

# Initialize FastAPI app
app = FastAPI(
    title="AI-Powered Product Search API",
    description="An AI-driven product search system using OpenAI, FAISS, and live store data.",
    version="1.0.0",
)

# Attach the imported limiter to the app state
app.state.limiter = limiter

# Add the exception handler to the app
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore

# Allow frontend apps to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all domains (change this in production!)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add the custom authentication middleware
# This should generally run before other app-specific logic but after CORS
app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(routes.router, prefix="/api", tags=["search"])
