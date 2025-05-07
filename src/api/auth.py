"""Authentication routes with security measures and rate limiting."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from src.dependencies import get_auth_service, limiter
from src.models.user import Token, UserCreate, UserLogin
from src.services.auth_service import AuthService
from src.utils import logger
from src.utils.config import JWT_ALGORITHM, JWT_SECRET_KEY

router = APIRouter()
security = HTTPBearer()


@router.post("/register")
@limiter.limit("10/hour;5/minute")
async def register(user: UserCreate, auth_service: AuthService = Depends(get_auth_service)):
    """
    Register a new user with validation.

    Args:
        user: User registration data

    Returns:
        Token: Access and refresh tokens

    Raises:
        HTTPException: If email format is invalid, password is weak, or email exists
    """
    # Validate email format and password strength
    if not auth_service.is_valid_email(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

    if not auth_service.is_strong_password(user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too weak")

    if await auth_service.get_user(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user_in_db = await auth_service.create_user(user)
    access_token, refresh_token = await auth_service.create_tokens(user_in_db.email)
    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post("/login")
@limiter.limit("20/hour;10/minute")
async def login(user: UserLogin, auth_service: AuthService = Depends(get_auth_service)):
    """
    Login with brute force protection.

    Args:
        user: Login credentials

    Returns:
        Token: Access and refresh tokens

    Raises:
        HTTPException: If credentials are invalid or too many failed attempts
    """
    return await auth_service.login(user)  # Use the new login method


@router.post("/refresh")
@limiter.limit("50/hour;20/minute")
async def refresh_token_handler(token: str, auth_service: AuthService = Depends(get_auth_service)):
    """
    Refresh access token using refresh token.

    Args:
        token: Refresh token

    Returns:
        dict: New access token

    Raises:
        HTTPException: If refresh token is invalid
    """
    new_token = await auth_service.refresh_access_token(token)
    if not new_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    return {"access_token": new_token, "token_type": "bearer"}


@router.post("/password/reset-request")
@limiter.limit("5/hour")
async def request_password_reset(email: str, auth_service: AuthService = Depends(get_auth_service)):
    """Request password reset token."""
    await auth_service.initiate_password_reset(email)
    return {"message": "If email exists, reset instructions have been sent"}


@router.post("/password/reset")
async def reset_password(token: str, new_password: str, auth_service: AuthService = Depends(get_auth_service)):
    """Complete password reset with token."""
    await auth_service.complete_password_reset(token, new_password)
    return {"message": "Password updated successfully"}


@router.post("/password/update")
async def update_password(
    request: Request,
    old_password: str,
    new_password: str,
    _auth: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Update user password."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not identify user from token. Middleware might not have run or token is invalid."
        )
    await auth_service.update_password(user_email, old_password, new_password)
    return {"message": "Password updated successfully"}


@router.get("/verify-email")
async def verify_user_email(token: str, auth_service: AuthService = Depends(get_auth_service)):
    """Verify user's email address using the provided token."""
    try:
        await auth_service.verify_email_token(token)
        # In a real frontend, you might redirect to a login page or success page.
        return {"message": "Email verified successfully. You can now log in."}
    except HTTPException as e:
        # Re-raise HTTPExceptions from auth_service directly
        raise e
    except Exception as e:
        # Catch any other unexpected errors
        logger.error("Unexpected error during email verification: %s for token %s", e, token)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during email verification.")


@router.post("/logout")
async def logout(
    auth: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Logs out the user by denylisting the current access token."""
    token_str = auth.credentials
    try:
        if not JWT_SECRET_KEY:
            logger.error("Logout attempt failed: JWT_SECRET_KEY is not configured.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server configuration error for logout.")

        payload = jwt.decode(
            token_str, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False}
        )  # Decode even if expired to get JTI
        access_jti = payload.get("jti")
        # Calculate remaining validity to set denylist TTL accurately
        # If token is already expired, exp_timestamp will be in the past.
        exp_timestamp = payload.get("exp", 0)
        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        # Denylist for at least a short period even if expired, or up to its original expiry
        # Max ensures we don't have negative TTL. Min ensures a short denylist period if already expired.
        denylist_ttl = max(0, exp_timestamp - current_timestamp)  # Time left until original expiry
        if denylist_ttl <= 0:  # Ensure a minimum denylist period even if token already expired
            denylist_ttl = 60  # Denylist for at least 60s

        if access_jti:
            await auth_service.add_jti_to_denylist(access_jti, denylist_ttl)
            logger.info("User %s logged out. Access token JTI %s denylisted.", payload.get("sub"), access_jti)
            return {"message": "Logout successful. Token has been invalidated."}
        else:
            logger.warning("Logout attempt with token missing JTI.")
            # Still return success as client expects logout, but log it.
            return {"message": "Logout processed. Token may not be fully invalidated if missing JTI."}

    except jwt.InvalidTokenError as e:
        # This can happen if the token is completely malformed, not just expired
        logger.warning("Logout attempt with invalid token: %s", e)
        # Even if token is invalid, client wants to logout, so don't error out here aggressively.
        # But a truly malformed token can't be denylisted by JTI.
        return {"message": "Logout processed. Token was invalid."}
    except Exception as e:
        logger.error("Error during logout: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing logout.")
