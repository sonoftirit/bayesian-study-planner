"""Calendar tests use a fake Google service, so they never touch the network."""

import datetime
import json
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

import planner.calendar_client as calendar_client
from planner.calendar_client import (
    CALENDAR_NAME,
    SCOPES,
    TIME_ZONE,
    build_event,
    create_event_for_action,
    delete_event,
    find_or_create_calendar,
)

DAY = datetime.date(2026, 11, 25)


def fake_service(calendar_pages=({"items": []},), created_calendar_id="new-id"):
    """A stand-in for the Google service that returns the given calendar list."""
    service = MagicMock()
    calendar_list = service.calendarList.return_value.list.return_value
    calendar_list.execute.side_effect = list(calendar_pages)
    insert_calendar = service.calendars.return_value.insert.return_value
    insert_calendar.execute.return_value = {"id": created_calendar_id}
    return service


def inserted_event(service):
    """The keyword arguments the code passed to events().insert()."""
    insert = service.events.return_value.insert
    insert.assert_called_once()
    return insert.call_args.kwargs


# --- Event bodies ------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "title", "end_time"),
    [
        ("Intense", "Intense study block", "15:00:00"),
        ("Light", "Light review session", "11:00:00"),
    ],
)
def test_timed_events_have_the_right_title_and_length(action, title, end_time):
    event = build_event(action, DAY)

    assert event["summary"] == title
    # Check the local clock time, not the UTC offset, because Vancouver's
    # offset depends on the installed time zone data.
    assert event["start"]["dateTime"].startswith("2026-11-25T10:00:00")
    assert event["end"]["dateTime"].startswith(f"2026-11-25T{end_time}")
    assert event["start"]["timeZone"] == "America/Vancouver"
    assert event["end"]["timeZone"] == "America/Vancouver"


def test_timed_event_times_carry_the_vancouver_offset():
    event = build_event("Light", DAY)
    start = datetime.datetime.fromisoformat(event["start"]["dateTime"])
    end = datetime.datetime.fromisoformat(event["end"]["dateTime"])

    expected = datetime.datetime(2026, 11, 25, 10, tzinfo=ZoneInfo(TIME_ZONE))
    assert start == expected
    assert end - start == datetime.timedelta(hours=1)


def test_rest_is_an_all_day_event():
    event = build_event("Rest", DAY)

    assert event["summary"] == "Rest day"
    # All-day events use "date" (no time); Google treats the end as exclusive.
    assert event["start"] == {"date": "2026-11-25"}
    assert event["end"] == {"date": "2026-11-26"}


def test_rest_day_on_new_years_eve_ends_next_year():
    event = build_event("Rest", datetime.date(2026, 12, 31))
    assert event["end"] == {"date": "2027-01-01"}


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError, match="Action must be one of"):
        build_event("Nap", DAY)


@pytest.mark.parametrize(
    "bad_date", [datetime.datetime(2026, 11, 25, 9, 30), "2026-11-25"]
)
def test_date_must_be_a_plain_date(bad_date):
    with pytest.raises(TypeError, match="datetime.date"):
        build_event("Rest", bad_date)


# --- Finding the Study Planner calendar --------------------------------------


def test_existing_calendar_is_reused():
    pages = [
        {
            "items": [
                {"id": "main", "summary": "Me"},
                {"id": "sp", "summary": CALENDAR_NAME},
            ]
        }
    ]
    service = fake_service(pages)

    assert find_or_create_calendar(service) == "sp"
    service.calendars.return_value.insert.assert_not_called()


def test_calendar_on_a_later_page_is_found():
    pages = [
        {"items": [{"id": "main", "summary": "Me"}], "nextPageToken": "page-2"},
        {"items": [{"id": "sp", "summary": CALENDAR_NAME}]},
    ]
    service = fake_service(pages)

    assert find_or_create_calendar(service) == "sp"
    list_calls = service.calendarList.return_value.list.call_args_list
    assert [call.kwargs["pageToken"] for call in list_calls] == [None, "page-2"]


def test_missing_calendar_is_created_in_vancouver_time():
    service = fake_service([{"items": [{"id": "main", "summary": "Me"}]}])

    assert find_or_create_calendar(service) == "new-id"
    service.calendars.return_value.insert.assert_called_once_with(
        body={"summary": CALENDAR_NAME, "timeZone": "America/Vancouver"}
    )


# --- Creating and deleting events --------------------------------------------


@pytest.mark.parametrize("action", ["Intense", "Light", "Rest"])
def test_event_goes_into_the_study_planner_calendar(action):
    service = fake_service([{"items": [{"id": "sp", "summary": CALENDAR_NAME}]}])

    create_event_for_action(action, DAY, service)

    kwargs = inserted_event(service)
    assert kwargs["calendarId"] == "sp"
    assert kwargs["body"] == build_event(action, DAY)


def test_created_event_is_returned():
    service = fake_service([{"items": [{"id": "sp", "summary": CALENDAR_NAME}]}])
    created = {"id": "evt", "htmlLink": "https://calendar.google.com/event?eid=x"}
    service.events.return_value.insert.return_value.execute.return_value = created

    assert create_event_for_action("Light", DAY, service) == created


def test_bad_input_makes_no_api_calls():
    service = fake_service()
    with pytest.raises(ValueError):
        create_event_for_action("Nap", DAY, service)
    assert service.mock_calls == []


def test_saved_login_is_used_when_no_service_is_given(monkeypatch):
    service = fake_service([{"items": [{"id": "sp", "summary": CALENDAR_NAME}]}])
    monkeypatch.setattr(calendar_client, "get_service", lambda: service)

    create_event_for_action("Rest", DAY)

    assert inserted_event(service)["calendarId"] == "sp"


def test_delete_event_targets_the_given_calendar():
    service = MagicMock()

    delete_event(service, "sp", "evt")

    service.events.return_value.delete.assert_called_once_with(
        calendarId="sp", eventId="evt"
    )


# --- Login -------------------------------------------------------------------


def write_token(path, scopes):
    """Save a token file shaped like the one Google's library writes."""
    token = {
        "token": "access",
        "refresh_token": "refresh",
        "client_id": "id",
        "client_secret": "secret",
        "scopes": scopes,
        "expiry": "2999-01-01T00:00:00Z",
    }
    path.write_text(json.dumps(token))


@pytest.fixture
def login(monkeypatch, tmp_path):
    """Point the login code at a temporary token file and a fake browser flow."""
    token_file = tmp_path / "token.json"
    monkeypatch.setattr(calendar_client, "TOKEN_FILE", token_file)
    flow_class = MagicMock()
    new_creds = (
        flow_class.from_client_secrets_file.return_value.run_local_server.return_value
    )
    new_creds.to_json.return_value = '{"new": "login"}'
    monkeypatch.setattr(calendar_client, "InstalledAppFlow", flow_class)
    return token_file, flow_class, new_creds


def test_saved_login_with_the_right_permissions_is_reused(login):
    token_file, flow_class, _ = login
    write_token(token_file, SCOPES)

    creds = calendar_client.get_credentials()

    assert creds.has_scopes(SCOPES)
    flow_class.from_client_secrets_file.assert_not_called()


def test_saved_login_with_old_permissions_asks_to_log_in_again(login):
    # The Stage 1.5 login only allowed calendar.events, which cannot create
    # the Study Planner calendar.
    token_file, flow_class, new_creds = login
    write_token(token_file, ["https://www.googleapis.com/auth/calendar.events"])

    creds = calendar_client.get_credentials()

    assert creds is new_creds
    flow_class.from_client_secrets_file.assert_called_once()
    assert flow_class.from_client_secrets_file.call_args.args[1] == SCOPES
    assert token_file.read_text() == '{"new": "login"}'


def test_first_run_opens_the_browser_login(login):
    token_file, flow_class, new_creds = login

    assert calendar_client.get_credentials() is new_creds
    assert token_file.read_text() == '{"new": "login"}'


def test_expired_login_is_refreshed_without_the_browser(login, monkeypatch):
    token_file, flow_class, _ = login
    token_file.write_text("{}")
    expired = MagicMock(valid=False, expired=True, refresh_token="refresh")
    expired.to_json.return_value = '{"refreshed": true}'
    fake_credentials = MagicMock()
    fake_credentials.from_authorized_user_file.return_value = expired
    monkeypatch.setattr(calendar_client, "Credentials", fake_credentials)

    assert calendar_client.get_credentials() is expired
    expired.refresh.assert_called_once()
    flow_class.from_client_secrets_file.assert_not_called()
    assert token_file.read_text() == '{"refreshed": true}'
