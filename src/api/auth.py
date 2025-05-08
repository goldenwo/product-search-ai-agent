"""Authentication routes with security measures and rate limiting."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.dependencies import get_auth_service, limiter
from src.models.user import Token, UserCreate, UserLogin
from src.services.auth_service import AuthService
from src.utils import logger
from src.utils.config import JWT_SECRET_KEY

router = APIRouter()
security = HTTPBearer()


@router.post("/register")
@limiter.limit("10/hour;5/minute")
async def register(request: Request, user: UserCreate, auth_service: AuthService = Depends(get_auth_service)):
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
async def login(request: Request, user: UserLogin, auth_service: AuthService = Depends(get_auth_service)):
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
async def refresh_token_handler(request: Request, token: str, auth_service: AuthService = Depends(get_auth_service)):
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
async def request_password_reset(request: Request, email: str, auth_service: AuthService = Depends(get_auth_service)):
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
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Logs out the user by denylisting the current access token JTI found in request state."""
    try:
        # Retrieve JTI and EXP directly from state set by middleware
        access_jti = getattr(request.state, "token_jti", None)
        exp_timestamp = getattr(request.state, "token_exp", None)
        user_email = getattr(request.state, "user_email", "Unknown User")  # Get email for logging

        if not access_jti:
            # This might happen if middleware failed or didn't run
            logger.warning("Logout attempt failed: JTI not found in request state for user %s.", user_email)
            # Return success to the client as they intended to logout, but log the issue.
            return {"message": "Logout processed, but token details were missing."}

        if not JWT_SECRET_KEY:  # Keep this check for safety
            logger.error("Logout attempt failed: JWT_SECRET_KEY is not configured.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server configuration error for logout.")

        # Calculate remaining validity from state
        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        denylist_ttl = 0
        if exp_timestamp:
            denylist_ttl = max(0, exp_timestamp - current_timestamp)
        if denylist_ttl <= 0:
            denylist_ttl = 60  # Ensure minimum denylist period

        # Denylist the JTI
        await auth_service.add_jti_to_denylist(access_jti, denylist_ttl)
        logger.info("User %s logged out. Access token JTI %s denylisted.", user_email, access_jti)
        return {"message": "Logout successful. Token has been invalidated."}

    except HTTPException as http_exc:  # Re-raise HTTPExceptions
        raise http_exc
    except Exception as e:
        user_email = getattr(request.state, "user_email", "Unknown User")  # Get email for logging
        logger.error("Error during logout for user %s: %s", user_email, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing logout.")
