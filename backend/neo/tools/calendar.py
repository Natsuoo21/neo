"""Google Calendar tool — Read/write calendar events via Google API."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build

from neo.tools.google_auth import get_credentials

logger = logging.getLogger(__name__)


def _get_service() -> Any:
    """Build and return the Google Calendar API service."""
    creds = get_credentials()
    if creds is None:
        raise RuntimeError(
            "Google Calendar not authenticated. Run OAuth flow first via Settings."
        )

    return build("calendar", "v3", credentials=creds)


def list_events(days: int = 7, max_results: int = 20) -> str:
    """List upcoming calendar events.

    Args:
        days: Number of days to look ahead.
        max_results: Maximum number of events to return.

    Returns:
        Formatted string of events.
    """
    service = _get_service()

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = result.get("items", [])
    if not events:
        return f"No events found in the next {days} days."

    lines = [f"Calendar events (next {days} days):\n"]
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        summary = event.get("summary", "(No title)")
        event_id = event.get("id", "")
        attendees = event.get("attendees", [])
        attendee_str = ", ".join(a.get("email", "") for a in attendees[:3])

        line = f"- {start}: {summary}"
        if attendee_str:
            line += f" [with: {attendee_str}]"
        line += f" (id: {event_id})"
        lines.append(line)

    return "\n".join(lines)


def create_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | None = None,
    description: str = "",
) -> str:
    """Create a calendar event.

    Args:
        title: Event title.
        start_time: ISO 8601 start time.
        end_time: ISO 8601 end time.
        attendees: List of email addresses.
        description: Event description.

    Returns:
        Confirmation string with event link.
    """
    service = _get_service()

    event_body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }

    if description:
        event_body["description"] = description

    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]

    event = service.events().insert(calendarId="primary", body=event_body).execute()

    link = event.get("htmlLink", "")
    return f"Event created: {title} ({start_time} to {end_time}). Link: {link}"


def update_event(event_id: str, **changes: Any) -> str:
    """Update a calendar event.

    Args:
        event_id: The event ID to update.
        **changes: Fields to update (title, start_time, end_time, description).

    Returns:
        Confirmation string.
    """
    service = _get_service()

    # Get existing event
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    if "title" in changes:
        event["summary"] = changes["title"]
    if "start_time" in changes:
        event["start"] = {"dateTime": changes["start_time"]}
    if "end_time" in changes:
        event["end"] = {"dateTime": changes["end_time"]}
    if "description" in changes:
        event["description"] = changes["description"]

    updated = (
        service.events()
        .update(calendarId="primary", eventId=event_id, body=event)
        .execute()
    )

    return f"Event updated: {updated.get('summary', event_id)}"


def delete_event(event_id: str) -> str:
    """Delete a calendar event. (DESTRUCTIVE — requires confirmation.)

    Args:
        event_id: The event ID to delete.

    Returns:
        Confirmation string.
    """
    service = _get_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return f"Event deleted: {event_id}"
