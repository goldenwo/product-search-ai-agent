"""Email service for sending notifications using SendGrid."""

import logging
from typing import Optional

from sendgrid.helpers.mail import Mail

from src.services.clients.sendgrid_client import SendGridClient
from src.utils.config import EMAIL_SENDER, FRONTEND_URL, IS_DEVELOPMENT, VERIFICATION_TOKEN_EXPIRE_HOURS

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

        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
        html_content = self._create_reset_email_template(username, reset_link)
        message = Mail(from_email=self.sender, to_emails=email, subject="Password Reset Request", html_content=html_content)

        try:
            if self.client:
                success = self.client.send_mail(message)
                if success:
                    logger.info("✉️ Reset email sent to %s", email)
                return success
            return False
        except Exception as e:
            logger.error("❌ Failed to send reset email to %s: %s", email, e)
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

    async def send_password_change_notification(self, email: str, username: str) -> bool:
        """
        Send password change notification email.

        Args:
            email: Recipient email address
            username: User's name for personalization

        Returns:
            bool: True if email was sent successfully
        """
        if IS_DEVELOPMENT:
            logger.info("Password change notification email would be sent to %s for user %s", email, username)
            return True

        subject = "Your Password Has Been Changed"
        html_content = self._create_password_change_template(username)
        message = Mail(from_email=self.sender, to_emails=email, subject=subject, html_content=html_content)

        try:
            if self.client:
                success = self.client.send_mail(message)
                if success:
                    logger.info("✉️ Password change notification sent to %s", email)
                return success
            return False
        except Exception as e:
            logger.error("❌ Failed to send password change notification to %s: %s", email, e)
            return False

    def _create_password_change_template(self, username: str) -> str:
        """
        Create HTML email template for password change notification.

        Args:
            username: User's name for personalization

        Returns:
            str: HTML content for the email
        """
        return f"""
        <h2>Hello {username},</h2>
        <p>This email confirms that your password has been successfully changed.</p>
        <p>If you did not make this change, please contact our support team immediately.</p>
        <p>Thank you,</p>
        <p>The Product Search AI Team</p>
        """

    async def send_verification_email(self, email: str, username: str, token: str) -> bool:
        """
        Send account verification email with a unique token link.

        Args:
            email: Recipient email address
            username: User's name for personalization
            token: Verification token for the link

        Returns:
            bool: True if email was sent successfully
        """
        if IS_DEVELOPMENT:
            logger.info("Account verification email would be sent to %s for user %s with token %s", email, username, token)
            return True

        verification_link = f"{FRONTEND_URL}/verify-email?token={token}"
        subject = "Verify Your Email Address - Product Search AI"
        html_content = self._create_verification_email_template(username, verification_link)
        message = Mail(from_email=self.sender, to_emails=email, subject=subject, html_content=html_content)

        try:
            if self.client:
                success = self.client.send_mail(message)
                if success:
                    logger.info("✉️ Verification email sent to %s", email)
                return success
            return False
        except Exception as e:
            logger.error("❌ Failed to send verification email to %s: %s", email, e)
            return False

    def _create_verification_email_template(self, username: str, verification_link: str) -> str:
        """
        Create HTML email template for account verification.

        Args:
            username: User's name for personalization
            verification_link: Account verification link

        Returns:
            str: HTML content for the email
        """
        return f"""
        <h2>Welcome {username}!</h2>
        <p>Thanks for signing up for Product Search AI. Please verify your email address by clicking the link below:</p>
        <p><a href="{verification_link}">{verification_link}</a></p>
        <p>This link will expire in {VERIFICATION_TOKEN_EXPIRE_HOURS} hours.</p>
        <p>If you didn't sign up for this account, please ignore this email.</p>
        <p>Thank you,</p>
        <p>The Product Search AI Team</p>
        """
