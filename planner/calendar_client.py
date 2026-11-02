"""Google Calendar connection: OAuth login and event creation.

Run `python -m planner.calendar_client` to log in and create one test event.
"""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Lets the app create and change events only, not read calendar settings or sharing.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TIME_ZONE = "America/Vancouver"
CREDENTIALS_FILE = Path("credentials.json")  # OAuth client from Google Cloud
TOKEN_FILE = Path("token.json")  # saved login, so the browser opens only once


def get_credentials():
    """Return valid credentials, logging in through the browser if needed."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
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


def create_test_event(service, start):
    """Create a 30-minute connection-test event at `start` and return it."""
    end = start + datetime.timedelta(minutes=30)
    event = {
        "summary": "Study Planner connection test",
        "start": {"dateTime": start.isoformat(), "timeZone": TIME_ZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIME_ZONE},
    }
    return service.events().insert(calendarId="primary", body=event).execute()


def delete_event(service, event_id):
    """Delete an event from the primary calendar."""
    service.events().delete(calendarId="primary", eventId=event_id).execute()


def main():
    service = get_service()
    now = datetime.datetime.now(ZoneInfo(TIME_ZONE)).replace(microsecond=0)
    event = create_test_event(service, now)
    print("Created event:", event["htmlLink"])
    print("Event ID:", event["id"])


if __name__ == "__main__":
    main()
