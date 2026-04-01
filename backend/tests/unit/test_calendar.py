"""Tests for neo.tools.calendar — Google Calendar API (mocked)."""

from unittest.mock import MagicMock, patch

import pytest


class TestListEvents:
    def test_list_events(self):
        mock_service = MagicMock()
        mock_events = mock_service.events.return_value
        mock_list = mock_events.list.return_value
        mock_list.execute.return_value = {
            "items": [
                {
                    "id": "evt1",
                    "summary": "Team Meeting",
                    "start": {"dateTime": "2026-04-01T10:00:00Z"},
                    "attendees": [{"email": "bob@test.com"}],
                },
                {
                    "id": "evt2",
                    "summary": "Lunch",
                    "start": {"date": "2026-04-01"},
                    "attendees": [],
                },
            ]
        }

        with (
            patch("neo.tools.calendar.get_credentials", return_value=MagicMock()),
            patch("neo.tools.calendar.build", return_value=mock_service),
        ):
            from neo.tools.calendar import list_events
            result = list_events(days=7)

            assert "Team Meeting" in result
            assert "Lunch" in result
            assert "evt1" in result

    def test_no_events(self):
        mock_service = MagicMock()
        mock_service.events.return_value.list.return_value.execute.return_value = {"items": []}

        with (
            patch("neo.tools.calendar.get_credentials", return_value=MagicMock()),
            patch("neo.tools.calendar.build", return_value=mock_service),
        ):
            from neo.tools.calendar import list_events
            result = list_events()
            assert "No events found" in result


class TestCreateEvent:
    def test_create_event(self):
        mock_service = MagicMock()
        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "htmlLink": "https://calendar.google.com/event/123",
        }

        with (
            patch("neo.tools.calendar.get_credentials", return_value=MagicMock()),
            patch("neo.tools.calendar.build", return_value=mock_service),
        ):
            from neo.tools.calendar import create_event
            result = create_event(
                title="Test Event",
                start_time="2026-04-01T10:00:00Z",
                end_time="2026-04-01T11:00:00Z",
                attendees=["alice@test.com"],
                description="A test event",
            )

            assert "Event created" in result
            assert "Test Event" in result


class TestUpdateEvent:
    def test_update_event(self):
        mock_service = MagicMock()
        mock_service.events.return_value.get.return_value.execute.return_value = {
            "summary": "Old Title",
            "start": {"dateTime": "2026-04-01T10:00:00Z"},
            "end": {"dateTime": "2026-04-01T11:00:00Z"},
        }
        mock_service.events.return_value.update.return_value.execute.return_value = {
            "summary": "New Title",
        }

        with (
            patch("neo.tools.calendar.get_credentials", return_value=MagicMock()),
            patch("neo.tools.calendar.build", return_value=mock_service),
        ):
            from neo.tools.calendar import update_event
            result = update_event("evt1", title="New Title")
            assert "Event updated" in result
            assert "New Title" in result


class TestDeleteEvent:
    def test_delete_event(self):
        mock_service = MagicMock()
        mock_service.events.return_value.delete.return_value.execute.return_value = None

        with (
            patch("neo.tools.calendar.get_credentials", return_value=MagicMock()),
            patch("neo.tools.calendar.build", return_value=mock_service),
        ):
            from neo.tools.calendar import delete_event
            result = delete_event("evt1")
            assert "Event deleted" in result


class TestNotAuthenticated:
    def test_raises_when_not_authenticated(self):
        with patch("neo.tools.calendar.get_credentials", return_value=None):
            from neo.tools.calendar import list_events
            with pytest.raises(RuntimeError, match="not authenticated"):
                list_events()
