"""Test the EmailService."""

from unittest.mock import Mock, create_autospec, patch

import pytest
from sendgrid.helpers.mail import From, HtmlContent, Mail, Subject, To

from src.services.email_service import EmailService


@pytest.fixture
def mock_mail():
    """Create a mock SendGrid Mail object."""
    mail = create_autospec(Mail)
    mail.from_email = From("noreply@yourdomain.com")
    mail.to_emails = To("test@example.com")
    mail.subject = Subject("Password Reset Request")
    mail.html_content = HtmlContent("")
    return mail


@pytest.fixture
def email_service(mock_mail):
    """Create EmailService with mocked SendGrid client."""
    with patch("sendgrid.helpers.mail.Mail", return_value=mock_mail):
        service = EmailService()
        service.client = Mock()
        service.client.send = Mock()
        return service


@pytest.mark.asyncio
async def test_send_reset_email_production(email_service):
    """Test sending reset email in production mode."""
    with patch("src.services.email_service.IS_DEVELOPMENT", False):
        await email_service.send_reset_email(email="test@example.com", token="test-token", username="testuser")

        # Verify email was sent
        email_service.client.send.assert_called_once()
        sent_mail = email_service.client.send.call_args[0][0]  # type: ignore[index]

        # Verify content through string representation
        mail_str = str(sent_mail)
        assert all(text in mail_str for text in ["test@example.com", "test-token", "testuser"])


@pytest.mark.asyncio
async def test_send_reset_email_development(email_service, caplog):
    """Test sending reset email in development mode."""
    caplog.set_level("INFO")  # Set log level to capture INFO messages

    with patch("src.services.email_service.IS_DEVELOPMENT", True):
        await email_service.send_reset_email(email="test@example.com", token="test-token", username="testuser")

        # Verify email was logged but not sent
        email_service.client.send.assert_not_called()
        assert "would be sent to test@example.com" in caplog.text


@pytest.mark.asyncio
async def test_send_reset_email_error(email_service, mock_mail):
    """Test error handling when sending email."""
    with patch("src.services.email_service.IS_DEVELOPMENT", False):
        email_service.client.send.side_effect = Exception("SendGrid error")

        with pytest.raises(Exception):
            await email_service.send_reset_email(email="test@example.com", token="test-token", username="testuser")
