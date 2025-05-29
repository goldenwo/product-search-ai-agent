"""Custom FastAPI Middleware Definitions."""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
import jwt
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
    "/auth/password/reset-request",
    "/auth/password/reset",
    "/auth/verify-email",
    "/api/",  # Health check route
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to verify JWT tokens for protected routes and attach user identity to request state.

    Checks for a 'Bearer' token in the 'Authorization' header for non-public paths.
    If valid, decodes user email and attaches it to `request.state.user_email`.
    Handles common JWT errors (missing, expired, invalid) with appropriate HTTP responses.
    Public paths (like /docs, /openapi.json, /auth/*) are explicitly excluded.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_path = request.url.path

        # 1. Check if route is public
        if request_path.startswith("/docs") or request_path.startswith("/openapi"):
            logger.debug("Allowing public access to OpenAPI/docs: %s", request_path)
            response = await call_next(request)
            return response

        # Check against explicitly defined public paths
        if request_path in PUBLIC_PATHS:
            logger.debug("Allowing public access to: %s", request_path)
            response = await call_next(request)
            return response

        logger.debug("Protected route, performing authentication for: %s", request_path)

        # 2. Extract Token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning("Auth header missing or invalid for protected route: %s", request_path)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header.split("Bearer ")[1]

        # 3. Verify Token & Populate State
        try:
            if not JWT_SECRET_KEY:
                logger.error("JWT_SECRET_KEY is not configured on the server.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server configuration error.")

            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

            email: str | None = payload.get("sub")
            token_type: str | None = payload.get("type")
            access_jti: str | None = payload.get("jti")

            # Check if JTI is denylisted
            temp_auth_service = request.app.state.auth_service

            if await temp_auth_service.is_jti_denylisted(access_jti):
                logger.warning("Denylisted access token presented for user: %s, JTI: %s", email, access_jti)
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token has been revoked"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Ensure it's a valid 'access' token with an email subject
            if not email or token_type != "access":
                logger.warning("Invalid token type ('%s') or missing subject for: %s", token_type, request_path)
                raise jwt.InvalidTokenError("Invalid token type or content")

            # 4. Attach user email and token details to request.state for downstream use
            request.state.user_email = email
            request.state.token_jti = access_jti
            request.state.token_exp = payload.get("exp")
            logger.debug("Authenticated user '%s' via middleware for path %s (JTI: %s)", email, request_path, access_jti)

        except jwt.ExpiredSignatureError:
            logger.warning("Expired token received for protected route: %s", request_path)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token for protected route: %s - Error: %s", request_path, e)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": f"Invalid token: {e}"},  # Keep f-string here if exception needs direct inclusion
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
        except HTTPException as http_exc:
            raise http_exc
        except Exception as e:
            logger.exception("Unexpected error during middleware auth verification for %s: %s", request_path, e)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error during authentication process."},
            )

        # 5. Proceed to next middleware/rate limiter/route
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.exception("Error after auth middleware for %s (User: %s): %s", request_path, getattr(request.state, "user_email", "N/A"), e)
            raise
