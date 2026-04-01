"""Gmail tool — Read/send emails via Gmail API."""

import base64
import logging
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build

from neo.tools.google_auth import get_credentials

logger = logging.getLogger(__name__)


def _get_service() -> Any:
    """Build and return the Gmail API service."""
    creds = get_credentials()
    if creds is None:
        raise RuntimeError(
            "Gmail not authenticated. Run OAuth flow first via Settings."
        )

    return build("gmail", "v1", credentials=creds)


def list_emails(query: str = "is:unread", limit: int = 10) -> str:
    """List emails matching a query.

    Args:
        query: Gmail search query (e.g., "is:unread", "from:boss@company.com").
        limit: Maximum number of emails to return.

    Returns:
        Formatted string of email summaries.
    """
    service = _get_service()

    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=limit)
        .execute()
    )

    messages = result.get("messages", [])
    if not messages:
        return f"No emails found matching: {query}"

    lines = [f"Emails matching '{query}':\n"]
    for msg_ref in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["Subject", "From", "Date"])
            .execute()
        )

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(No subject)")
        sender = headers.get("From", "Unknown")
        date = headers.get("Date", "")
        snippet = msg.get("snippet", "")

        lines.append(f"- [{msg_ref['id']}] {subject}")
        lines.append(f"  From: {sender} | Date: {date}")
        lines.append(f"  {snippet[:100]}...")

    return "\n".join(lines)


def read_email(email_id: str) -> str:
    """Read a full email by ID.

    Args:
        email_id: The Gmail message ID.

    Returns:
        Formatted email content.
    """
    service = _get_service()

    msg = (
        service.users()
        .messages()
        .get(userId="me", id=email_id, format="full")
        .execute()
    )

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    subject = headers.get("Subject", "(No subject)")
    sender = headers.get("From", "Unknown")
    to = headers.get("To", "Unknown")
    date = headers.get("Date", "")

    # Extract body
    body = _extract_body(msg.get("payload", {}))

    return (
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"To: {to}\n"
        f"Date: {date}\n"
        f"ID: {email_id}\n\n"
        f"{body}"
    )


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. (DESTRUCTIVE — requires confirmation.)

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text.

    Returns:
        Confirmation string.
    """
    service = _get_service()

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )

    return f"Email sent to {to}: '{subject}' (id: {result.get('id', 'unknown')})"


def reply_to(email_id: str, body: str) -> str:
    """Reply to an email. (DESTRUCTIVE — requires confirmation.)

    Args:
        email_id: The Gmail message ID to reply to.
        body: Reply body text.

    Returns:
        Confirmation string.
    """
    service = _get_service()

    # Get original message for headers
    original = (
        service.users()
        .messages()
        .get(userId="me", id=email_id, format="metadata", metadataHeaders=["Subject", "From", "Message-ID"])
        .execute()
    )

    headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
    subject = headers.get("Subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    sender = headers.get("From", "")
    thread_id = original.get("threadId", "")

    message = MIMEText(body)
    message["to"] = sender
    message["subject"] = subject
    if "Message-ID" in headers:
        message["In-Reply-To"] = headers["Message-ID"]
        message["References"] = headers["Message-ID"]

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    send_body: dict[str, Any] = {"raw": raw}
    if thread_id:
        send_body["threadId"] = thread_id

    result = (
        service.users()
        .messages()
        .send(userId="me", body=send_body)
        .execute()
    )

    return f"Reply sent to {sender}: '{subject}' (id: {result.get('id', 'unknown')})"


def _extract_body(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    # Direct body
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Multipart — search for text/plain part
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Fallback to HTML
    for part in parts:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return "(No readable content)"
