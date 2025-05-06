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

# Attach limiter to app state for use by handlers/dependencies if needed
app.state.limiter = limiter

# Add rate limit exceeded exception handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # WARNING: Allow all domains for dev; restrict in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom authentication middleware (runs after CORS, before routes)
app.add_middleware(AuthMiddleware)

# Include API routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(routes.router, prefix="/api", tags=["search"])
