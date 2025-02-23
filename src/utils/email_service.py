"""Email service for sending notifications using SendGrid."""

import logging
from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.utils.config import EMAIL_SENDER, FRONTEND_URL, IS_DEVELOPMENT, SENDGRID_API_KEY

logger = logging.getLogger(__name__)


class EmailService:
    """Handles email notifications using SendGrid."""

    def __init__(self):
        self.client: Optional[SendGridAPIClient] = SendGridAPIClient(SENDGRID_API_KEY) if not IS_DEVELOPMENT else None
        self.sender = EMAIL_SENDER

    async def send_reset_email(self, email: str, token: str, username: str) -> None:
        """Send password reset email via SendGrid."""
        if IS_DEVELOPMENT:
            logger.info("Password reset email would be sent to %s with token %s", email, token)
            return

        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
        html_content = f"""
        <h2>Hello {username},</h2>
        <p>We received a request to reset your password.</p>
        <p>Click the link below to reset your password:</p>
        <p><a href="{reset_link}">{reset_link}</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request this reset, please ignore this email.</p>
        """

        message = Mail(from_email=self.sender, to_emails=email, subject="Password Reset Request", html_content=html_content)

        try:
            await self._send_email(message)
            logger.info("✉️ Reset email sent to %s", email)
        except Exception as e:
            logger.error("❌ Failed to send reset email to %s: %s", email, str(e))
            raise

    async def _send_email(self, message: Mail) -> None:
        """Send email using SendGrid."""
        try:
            if self.client is None:
                return None
            self.client.send(message)
        except Exception as e:
            logger.error("❌ SendGrid error: %s", str(e))
            raise
