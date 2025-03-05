"""Email service for sending notifications using SendGrid."""

import logging
from typing import Optional

from sendgrid.helpers.mail import Mail

from src.services.clients.sendgrid_client import SendGridClient
from src.utils.config import EMAIL_SENDER, FRONTEND_URL, IS_DEVELOPMENT

logger = logging.getLogger(__name__)


class EmailService:
    """
    Handles email notifications and templating.

    Provides business logic layer for email communications,
    including template rendering and delivery status tracking.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Email service with SendGrid client.

        Args:
            api_key: Optional API key override
        """
        self.client = SendGridClient(api_key=api_key) if not IS_DEVELOPMENT else None
        self.sender = EMAIL_SENDER

    async def send_reset_email(self, email: str, token: str, username: str) -> bool:
        """
        Send password reset email with token link.

        Args:
            email: Recipient email address
            token: Reset token for the link
            username: User's name for personalization

        Returns:
            bool: True if email was sent successfully

        Raises:
            Exception: If sending fails and not in development mode
        """
        if IS_DEVELOPMENT:
            logger.info("Password reset email would be sent to %s with token %s", email, token)
            return True

        # Create reset link for email
        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"

        # Construct email template
        html_content = self._create_reset_email_template(username, reset_link)

        # Create mail object
        message = Mail(from_email=self.sender, to_emails=email, subject="Password Reset Request", html_content=html_content)

        try:
            # Send email via client
            if self.client:
                success = self.client.send_mail(message)
                if success:
                    logger.info("✉️ Reset email sent to %s", email)
                return success
            return False
        except Exception as e:
            logger.error("❌ Failed to send reset email to %s: %s", email, str(e))
            raise

    def _create_reset_email_template(self, username: str, reset_link: str) -> str:
        """
        Create HTML email template for password reset.

        Args:
            username: User's name for personalization
            reset_link: Password reset link

        Returns:
            str: HTML content for the email
        """
        return f"""
        <h2>Hello {username},</h2>
        <p>We received a request to reset your password.</p>
        <p>Click the link below to reset your password:</p>
        <p><a href="{reset_link}">{reset_link}</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request this reset, please ignore this email.</p>
        """
