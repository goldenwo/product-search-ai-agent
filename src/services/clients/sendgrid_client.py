"""Client for interacting with SendGrid API."""

from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.utils import logger
from src.utils.config import SENDGRID_API_KEY


class SendGridClient:
    """
    Client for making requests to the SendGrid API.

    Handles raw API interactions for sending emails.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize SendGrid API client.

        Args:
            api_key: Optional API key override
        """
        self.api_key = api_key or SENDGRID_API_KEY
        self.client = SendGridAPIClient(self.api_key) if self.api_key else None

    def send_mail(self, message: Mail) -> bool:
        """
        Send an email via SendGrid API.

        Args:
            message: Mail object to send

        Returns:
            bool: True if successful, False otherwise

        Raises:
            Exception: If the API call fails
        """
        if not self.client:
            logger.warning("⚠️ No SendGrid client available, email not sent")
            return False

        try:
            response = self.client.send(message)
            status_code = response.status_code

            # Use string representation to check success status
            status_str = str(status_code)
            if status_str.startswith("2"):
                logger.info("✅ Email sent successfully (Status: %s)", status_str)
                return True
            else:
                logger.error("❌ SendGrid API error: Status %s", status_str)
                return False

        except Exception as e:
            logger.error("❌ SendGrid API error: %s", e)
            raise
