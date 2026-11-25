"""Google Calendar: OAuth login and turning an action into a calendar event.

Events go into a separate "Study Planner" calendar, so the main calendar stays
clean. Run `python -m planner.calendar_client` to log in and check the
connection; it finds (or creates) that calendar without adding any events.
"""

import datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    # Create the app's own calendars, and manage events only in those. The app
    # cannot read or change events in any other calendar, including the main one.
    "https://www.googleapis.com/auth/calendar.app.created",
    # See the names of the user's calendars (not their events), so the app can
    # find its "Study Planner" calendar again on later runs.
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
TIME_ZONE = "America/Vancouver"
CREDENTIALS_FILE = Path("credentials.json")  # OAuth client from Google Cloud
TOKEN_FILE = Path("token.json")  # saved login, so the browser opens only once

CALENDAR_NAME = "Study Planner"
STUDY_START = datetime.time(10, 0)  # timed study sessions start at 10:00


class EventType(NamedTuple):
    """What an action looks like in the calendar."""

    title: str
    hours: int | None  # None means an all-day event


EVENT_TYPES = {
    "Intense": EventType("Intense study block", 5),
    "Light": EventType("Light review session", 1),
    "Rest": EventType("Rest day", None),
}


def get_credentials():
    """Return valid credentials, logging in through the browser if needed."""
    creds = None
    if TOKEN_FILE.exists():
        # Load without passing SCOPES: passing them would overwrite the scopes
        # the saved login was really granted, and hide a missing permission.
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
        if not creds.has_scopes(SCOPES):
            creds = None  # permissions changed, so the user must log in again
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        # port=0 picks any free local port for Google to redirect back to.
        creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def get_service():
    """Build a Google Calendar API client using the saved login."""
    return build("calendar", "v3", credentials=get_credentials())


def find_or_create_calendar(service):
    """Return the ID of the "Study Planner" calendar, creating it if needed."""
    page_token = None
    while True:
        # Google returns the calendar list in pages; follow them all.
        page = service.calendarList().list(pageToken=page_token).execute()
        for calendar in page.get("items", []):
            if calendar.get("summary") == CALENDAR_NAME:
                return calendar["id"]
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    body = {"summary": CALENDAR_NAME, "timeZone": TIME_ZONE}
    return service.calendars().insert(body=body).execute()["id"]


def build_event(action, date):
    """Return the Google Calendar event body for `action` on `date`.

    Intense and Light are timed sessions starting at STUDY_START in Vancouver
    time. Rest is an all-day event; Google treats its end date as exclusive,
    so a one-day event ends on the next day.
    """
    if action not in EVENT_TYPES:
        raise ValueError(f"Action must be one of {list(EVENT_TYPES)}, got {action!r}.")
    # A datetime is also a date in Python, but its time part would end up in an
    # all-day event, so insist on a plain date.
    if isinstance(date, datetime.datetime) or not isinstance(date, datetime.date):
        raise TypeError(f"date must be a datetime.date, got {date!r}.")

    event_type = EVENT_TYPES[action]
    event = {
        "summary": event_type.title,
        "description": "Recommended by the Bayesian study planner.",
    }
    if event_type.hours is None:
        next_day = date + datetime.timedelta(days=1)
        event["start"] = {"date": date.isoformat()}
        event["end"] = {"date": next_day.isoformat()}
    else:
        start = datetime.datetime.combine(date, STUDY_START, ZoneInfo(TIME_ZONE))
        end = start + datetime.timedelta(hours=event_type.hours)
        event["start"] = {"dateTime": start.isoformat(), "timeZone": TIME_ZONE}
        event["end"] = {"dateTime": end.isoformat(), "timeZone": TIME_ZONE}
    return event


def create_event_for_action(action, date, service=None):
    """Add the event for `action` on `date` to the Study Planner calendar.

    Returns the created event, which includes its "htmlLink". `service` can be
    passed in (the tests pass a fake one); otherwise the saved login is used.
    """
    event = build_event(action, date)  # check the input before any network call
    if service is None:
        service = get_service()
    calendar_id = find_or_create_calendar(service)
    return service.events().insert(calendarId=calendar_id, body=event).execute()


def delete_event(service, calendar_id, event_id):
    """Delete one event, for example to clean up after a manual test."""
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def main():
    calendar_id = find_or_create_calendar(get_service())
    print(f"Connected. The {CALENDAR_NAME!r} calendar has ID {calendar_id}")


if __name__ == "__main__":
    main()
