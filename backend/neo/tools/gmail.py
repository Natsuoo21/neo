"""Gmail tool — Read/send professional emails via Gmail API.

Supports HTML email body, CC/BCC, file attachments, and signatures.
"""

import base64
import logging
import mimetypes
import os
import re
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build

from neo.tools.google_auth import get_credentials

logger = logging.getLogger(__name__)


def _get_service() -> Any:
    """Build and return the Gmail API service."""
    creds = get_credentials()
    if creds is None:
        raise RuntimeError("Gmail not authenticated. Run OAuth flow first via Settings.")

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Markdown → HTML converter (lightweight, no external deps)
# ---------------------------------------------------------------------------
def _markdown_to_html(text: str) -> str:
    """Convert simple markdown text to clean HTML for email.

    Supports: **bold**, *italic*, bullet lists (- ), numbered lists (1. ),
    blank lines as paragraph breaks, and links.
    """
    lines = text.split("\n")
    html_parts: list[str] = []
    in_ul = False
    in_ol = False

    for line in lines:
        stripped = line.strip()

        # Close lists if we're leaving them
        if in_ul and not stripped.startswith("- "):
            html_parts.append("</ul>")
            in_ul = False
        if in_ol and not re.match(r"^\d+\.\s", stripped):
            html_parts.append("</ol>")
            in_ol = False

        # Empty line = paragraph break
        if not stripped:
            html_parts.append("<br>")
            continue

        # Bullet list
        if stripped.startswith("- "):
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            content = _inline_md_to_html(stripped[2:])
            html_parts.append(f"<li>{content}</li>")
            continue

        # Numbered list
        num_match = re.match(r"^(\d+)\.\s(.+)", stripped)
        if num_match:
            if not in_ol:
                html_parts.append("<ol>")
                in_ol = True
            content = _inline_md_to_html(num_match.group(2))
            html_parts.append(f"<li>{content}</li>")
            continue

        # Normal paragraph
        content = _inline_md_to_html(stripped)
        html_parts.append(f"<p style='margin:0 0 8px 0;'>{content}</p>")

    # Close any open lists
    if in_ul:
        html_parts.append("</ul>")
    if in_ol:
        html_parts.append("</ol>")

    body_html = "\n".join(html_parts)
    return (
        f"<div style='font-family:Calibri,Arial,sans-serif;font-size:14px;"
        f"color:#333333;line-height:1.5;'>\n{body_html}\n</div>"
    )


def _inline_md_to_html(text: str) -> str:
    """Convert inline markdown to HTML: **bold**, *italic*."""
    # Bold: **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic: *text*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Underline: __text__
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    return text


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------
def _build_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    html_body: str | None = None,
    attachments: list[str] | None = None,
    signature: str | None = None,
) -> MIMEMultipart | MIMEText:
    """Build a MIME message with optional HTML, attachments, and signature.

    If html_body is provided, sends multipart/alternative (HTML + plain text).
    If html_body is not provided but body contains markdown, auto-generates HTML.
    If attachments are present, wraps in multipart/mixed.
    """
    # Append signature if provided
    full_body = body
    if signature:
        full_body = f"{body}\n\n--\n{signature}"

    # Determine if we need HTML
    has_markdown = any(marker in body for marker in ["**", "*", "- ", "1. "])
    use_html = html_body is not None or has_markdown

    if use_html:
        html_content = html_body if html_body else _markdown_to_html(full_body)
        if signature and html_body:
            # Append signature to provided HTML
            sig_html = f"<br><br><span style='color:#888;'>--<br>{signature.replace(chr(10), '<br>')}</span>"
            html_content = f"{html_content}{sig_html}"
    else:
        html_content = None

    # Build message parts
    has_attachments = attachments and len(attachments) > 0

    if has_attachments:
        msg = MIMEMultipart("mixed")

        if html_content:
            alt_part = MIMEMultipart("alternative")
            alt_part.attach(MIMEText(full_body, "plain", "utf-8"))
            alt_part.attach(MIMEText(html_content, "html", "utf-8"))
            msg.attach(alt_part)
        else:
            msg.attach(MIMEText(full_body, "plain", "utf-8"))

        # Attach files
        for file_path in attachments:
            expanded = os.path.expanduser(file_path)
            if not os.path.isfile(expanded):
                logger.warning(f"Attachment not found, skipping: {file_path}")
                continue

            content_type, _ = mimetypes.guess_type(expanded)
            if content_type is None:
                content_type = "application/octet-stream"
            main_type, sub_type = content_type.split("/", 1)

            with open(expanded, "rb") as f:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(f.read())

            from email import encoders
            encoders.encode_base64(attachment)
            filename = os.path.basename(expanded)
            attachment.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(attachment)

    elif html_content:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(full_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))
    else:
        msg = MIMEText(full_body, "plain", "utf-8")

    # Set headers
    msg["to"] = to
    msg["subject"] = subject
    if cc:
        msg["cc"] = cc
    if bcc:
        msg["bcc"] = bcc

    return msg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def list_emails(query: str = "is:unread", limit: int = 10) -> str:
    """List emails matching a query.

    Args:
        query: Gmail search query (e.g., "is:unread", "from:boss@company.com").
        limit: Maximum number of emails to return.

    Returns:
        Formatted string of email summaries.
    """
    service = _get_service()

    result = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()

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

    msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    subject = headers.get("Subject", "(No subject)")
    sender = headers.get("From", "Unknown")
    to = headers.get("To", "Unknown")
    date = headers.get("Date", "")

    # Extract body
    body = _extract_body(msg.get("payload", {}))

    return f"Subject: {subject}\nFrom: {sender}\nTo: {to}\nDate: {date}\nID: {email_id}\n\n{body}"


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    html_body: str | None = None,
    attachments: list[str] | None = None,
    signature: str | None = None,
) -> str:
    """Send an email with optional HTML formatting, CC/BCC, and attachments.

    (DESTRUCTIVE — requires confirmation.)

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text (plain text, or markdown for auto HTML conversion).
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
        html_body: Explicit HTML body. If not provided and body contains markdown,
                   HTML is auto-generated from the body text.
        attachments: List of file paths to attach.
        signature: Signature text to append.

    Returns:
        Confirmation string.
    """
    service = _get_service()

    message = _build_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        html_body=html_body,
        attachments=attachments,
        signature=signature,
    )

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    parts = [f"Email sent to {to}: '{subject}' (id: {result.get('id', 'unknown')})"]
    if cc:
        parts.append(f"CC: {cc}")
    if attachments:
        parts.append(f"Attachments: {', '.join(os.path.basename(a) for a in attachments)}")

    return " | ".join(parts)


def reply_to(
    email_id: str,
    body: str,
    cc: str = "",
    html_body: str | None = None,
    attachments: list[str] | None = None,
) -> str:
    """Reply to an email with optional HTML and attachments.

    (DESTRUCTIVE — requires confirmation.)

    Args:
        email_id: The Gmail message ID to reply to.
        body: Reply body text.
        cc: CC recipients (comma-separated).
        html_body: Explicit HTML body.
        attachments: List of file paths to attach.

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

    message = _build_message(
        to=sender,
        subject=subject,
        body=body,
        cc=cc,
        html_body=html_body,
        attachments=attachments,
    )

    if "Message-ID" in headers:
        message["In-Reply-To"] = headers["Message-ID"]
        message["References"] = headers["Message-ID"]

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    send_body: dict[str, Any] = {"raw": raw}
    if thread_id:
        send_body["threadId"] = thread_id

    result = service.users().messages().send(userId="me", body=send_body).execute()

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
