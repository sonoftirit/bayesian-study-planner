"""Calendar tests use a fake Google service, so they never touch the network."""

import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from planner.calendar_client import TIME_ZONE, create_test_event, delete_event


def test_create_test_event_sends_title_and_times():
    service = MagicMock()
    start = datetime.datetime(2026, 11, 2, 14, 0, tzinfo=ZoneInfo(TIME_ZONE))

    create_test_event(service, start)

    insert = service.events.return_value.insert
    insert.assert_called_once()
    kwargs = insert.call_args.kwargs
    assert kwargs["calendarId"] == "primary"
    body = kwargs["body"]
    assert body["summary"] == "Study Planner connection test"
    # Compare to isoformat() instead of a hard-coded UTC offset, because
    # Vancouver's offset depends on the installed time zone data.
    end = start + datetime.timedelta(minutes=30)
    assert body["start"] == {
        "dateTime": start.isoformat(),
        "timeZone": "America/Vancouver",
    }
    assert body["end"] == {"dateTime": end.isoformat(), "timeZone": "America/Vancouver"}


def test_create_test_event_returns_created_event():
    service = MagicMock()
    created = {"id": "abc123", "htmlLink": "https://calendar.google.com/event?eid=x"}
    service.events.return_value.insert.return_value.execute.return_value = created
    start = datetime.datetime(2026, 11, 2, 14, 0, tzinfo=ZoneInfo(TIME_ZONE))

    assert create_test_event(service, start) == created


def test_delete_event_targets_primary_calendar():
    service = MagicMock()

    delete_event(service, "abc123")

    service.events.return_value.delete.assert_called_once_with(
        calendarId="primary", eventId="abc123"
    )
