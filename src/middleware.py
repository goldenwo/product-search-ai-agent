"""Custom FastAPI Middleware Definitions."""

import jwt
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.utils import logger
from src.utils.config import JWT_ALGORITHM, JWT_SECRET_KEY

# Define paths that DO NOT require authentication
# Using explicit lists is often clearer than complex regex for common cases
PUBLIC_PATHS = {
    "/docs",
    "/openapi.json",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/auth/request-reset",
    "/auth/reset-password",
    "/api/",  # Health check route
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to verify JWT tokens for protected routes and attach user identity to request state.

    This middleware checks for a 'Bearer' token in the 'Authorization' header
    for requests targeting non-public API paths. If a valid access token is found,
    it decodes the user's email and attaches it to `request.state.user_email`.

    It handles common JWT errors (missing, expired, invalid) by returning
    appropriate HTTP 401 or 403 responses.

    Public paths (like /docs, /openapi.json, /auth/*) are explicitly excluded.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_path = request.url.path

        # --- 1. Check if route is public ---
        # Allow direct access to OpenAPI docs, auth endpoints, and health check
        if request_path in PUBLIC_PATHS or request_path.startswith("/docs") or request_path.startswith("/openapi"):
            logger.debug(f"Allowing public access to: {request_path}")
            response = await call_next(request)
            return response

        # --- All other /api routes (implicitly) require authentication ---
        # We assume paths not in PUBLIC_PATHS starting with /api need auth
        # Adjust this logic if your structure is different
        if not request_path.startswith("/api"):
            # If it's not public and not /api, it might be an unexpected path
            logger.warning(f"Request to non-API, non-public path: {request_path}")
            # Let it proceed, maybe another middleware handles it, or FastAPI returns 404
            response = await call_next(request)
            return response

        # --- 2. Extract Token ---
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"Auth header missing or invalid for protected route: {request_path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},  # Standard header for 401
            )

        token = auth_header.split("Bearer ")[1]

        # --- 3. Verify Token & Populate State ---
        try:
            if not JWT_SECRET_KEY:
                logger.error("JWT_SECRET_KEY is not configured on the server.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server configuration error.")

            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

            email: str | None = payload.get("sub")
            token_type: str | None = payload.get("type")

            # Ensure it's a valid 'access' token with an email subject
            if not email or token_type != "access":
                logger.warning(f"Invalid token type ('{token_type}') or missing subject for: {request_path}")
                raise jwt.InvalidTokenError("Invalid token type or content")

            # --- 4. Attach user email to request.state ---
            # This makes it available to downstream dependencies (like the rate limiter key func)
            request.state.user_email = email
            logger.debug(f"Authenticated user '{email}' via middleware for path {request_path}")

        except jwt.ExpiredSignatureError:
            logger.warning(f"Expired token received for protected route: {request_path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token for protected route: {request_path} - Error: {e}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,  # Use 401 for invalid token structure/signature issues
                content={"detail": f"Invalid token: {e}"},
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},  # More specific header
            )
        except HTTPException as http_exc:  # Re-raise specific HTTP exceptions
            raise http_exc
        except Exception as e:
            # Catch unexpected errors during verification
            logger.exception(f"Unexpected error during middleware auth verification for {request_path}: {e}")  # Use exception for stacktrace
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error during authentication process."},
            )

        # --- 5. Proceed to next middleware/rate limiter/route ---
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Catch errors raised further down the chain after auth passed
            logger.exception(f"Error after auth middleware for {request_path} (User: {getattr(request.state, 'user_email', 'N/A')}): {e}")
            # Depending on the error, you might want to return a generic 500
            # or let FastAPI's default exception handling take over
            raise  # Re-raise the exception for FastAPI handlers
