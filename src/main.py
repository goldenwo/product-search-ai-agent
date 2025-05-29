"""Main module for the AI-Powered Product Search API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api import auth, routes
from src.dependencies import get_email_service, get_redis_service, get_user_service, limiter
from src.middleware import AuthMiddleware
from src.services.auth_service import AuthService
from src.services.email_service import EmailService
from src.services.redis_service import RedisService
from src.services.user_service import UserService
from src.utils import logger


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Lifespan manager for the application.
    Handles startup and shutdown events.
    """
    # Startup logic
    logger.info("Application startup...")
    redis_s: RedisService = get_redis_service()
    user_s: UserService = get_user_service()
    email_s: EmailService = get_email_service()
    auth_s: AuthService = AuthService(redis_service=redis_s, user_service=user_s, email_service=email_s)
    application.state.auth_service = auth_s
    application.state.limiter = limiter
    logger.info("AuthService and Limiter initialized and attached to app.state.")

    yield

    # Shutdown logic (if any)
    logger.info("Application shutdown...")
    # Example: await some_service.close_connections()


# Initialize FastAPI app with lifespan manager
app = FastAPI(
    title="AI-Powered Product Search API",
    description="An AI-driven product search system using OpenAI, FAISS, and live store data.",
    version="1.0.0",
    lifespan=lifespan,
)

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

# Add rate limit exceeded exception handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore
