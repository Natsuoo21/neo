"""Tests for neo.tools.gmail — Gmail API (mocked)."""

import base64
from unittest.mock import MagicMock, patch

import pytest


class TestListEmails:
    def test_list_emails(self):
        mock_service = MagicMock()
        users = mock_service.users.return_value
        messages = users.messages.return_value

        messages.list.return_value.execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
        }

        messages.get.return_value.execute.return_value = {
            "snippet": "Hey, how are you?",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Hello"},
                    {"name": "From", "value": "alice@test.com"},
                    {"name": "Date", "value": "2026-04-01"},
                ]
            },
        }

        with (
            patch("neo.tools.gmail.get_credentials", return_value=MagicMock()),
            patch("neo.tools.gmail.build", return_value=mock_service),
        ):
            from neo.tools.gmail import list_emails
            result = list_emails(query="is:unread", limit=5)

            assert "Hello" in result
            assert "alice@test.com" in result

    def test_no_emails(self):
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": []
        }

        with (
            patch("neo.tools.gmail.get_credentials", return_value=MagicMock()),
            patch("neo.tools.gmail.build", return_value=mock_service),
        ):
            from neo.tools.gmail import list_emails
            result = list_emails()
            assert "No emails found" in result


class TestReadEmail:
    def test_read_email_plain_text(self):
        body_data = base64.urlsafe_b64encode(b"This is the email body").decode()
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "bob@test.com"},
                    {"name": "To", "value": "me@test.com"},
                    {"name": "Date", "value": "2026-04-01"},
                ],
                "body": {"data": body_data},
            }
        }

        with (
            patch("neo.tools.gmail.get_credentials", return_value=MagicMock()),
            patch("neo.tools.gmail.build", return_value=mock_service),
        ):
            from neo.tools.gmail import read_email
            result = read_email("msg1")

            assert "Test Subject" in result
            assert "bob@test.com" in result
            assert "This is the email body" in result

    def test_read_email_multipart(self):
        body_data = base64.urlsafe_b64encode(b"Plain text body").decode()
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "Subject", "value": "Multipart"},
                    {"name": "From", "value": "sender@test.com"},
                    {"name": "To", "value": "me@test.com"},
                    {"name": "Date", "value": "2026-04-01"},
                ],
                "body": {},
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": body_data}},
                    {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(b"<p>HTML</p>").decode()}},
                ],
            }
        }

        with (
            patch("neo.tools.gmail.get_credentials", return_value=MagicMock()),
            patch("neo.tools.gmail.build", return_value=mock_service),
        ):
            from neo.tools.gmail import read_email
            result = read_email("msg2")
            assert "Plain text body" in result


class TestSendEmail:
    def test_send_email(self):
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
            "id": "sent1"
        }

        with (
            patch("neo.tools.gmail.get_credentials", return_value=MagicMock()),
            patch("neo.tools.gmail.build", return_value=mock_service),
        ):
            from neo.tools.gmail import send_email
            result = send_email("alice@test.com", "Hello", "Body text")

            assert "Email sent" in result
            assert "alice@test.com" in result
            assert "sent1" in result


class TestReplyTo:
    def test_reply_to(self):
        mock_service = MagicMock()
        users = mock_service.users.return_value
        messages = users.messages.return_value

        # Original message
        messages.get.return_value.execute.return_value = {
            "threadId": "thread1",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Original Subject"},
                    {"name": "From", "value": "sender@test.com"},
                    {"name": "Message-ID", "value": "<abc@test.com>"},
                ]
            },
        }

        messages.send.return_value.execute.return_value = {"id": "reply1"}

        with (
            patch("neo.tools.gmail.get_credentials", return_value=MagicMock()),
            patch("neo.tools.gmail.build", return_value=mock_service),
        ):
            from neo.tools.gmail import reply_to
            result = reply_to("msg1", "Thanks!")

            assert "Reply sent" in result
            assert "sender@test.com" in result


class TestNotAuthenticated:
    def test_raises_when_not_authenticated(self):
        with patch("neo.tools.gmail.get_credentials", return_value=None):
            from neo.tools.gmail import list_emails
            with pytest.raises(RuntimeError, match="not authenticated"):
                list_emails()
