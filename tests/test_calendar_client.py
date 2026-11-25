"""Calendar tests use a fake Google service, so they never touch the network."""

import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

import planner.calendar_client as calendar_client
from planner.calendar_client import (
    CALENDAR_NAME,
    SCOPES,
    build_event,
    create_event_for_action,
    delete_event,
    find_or_create_calendar,
)

DAY = datetime.date(2026, 11, 25)
STUDY_PLANNER_ONLY = [{"items": [{"id": "sp", "summary": CALENDAR_NAME}]}]


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


def http_error(status):
    """An HttpError like the one the Google client raises for `status`."""
    return HttpError(MagicMock(status=status, reason="error"), b"{}")


# --- Event bodies ------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "title", "end"),
    [
        ("Intense", "Intense study block", "2026-11-25T15:00:00"),
        ("Light", "Light review session", "2026-11-25T11:00:00"),
    ],
)
def test_timed_events_have_the_right_title_and_length(action, title, end):
    event = build_event(action, DAY)

    assert event["summary"] == title
    # Local clock times with no UTC offset: Google applies the time zone.
    assert event["start"] == {
        "dateTime": "2026-11-25T10:00:00",
        "timeZone": "America/Vancouver",
    }
    assert event["end"] == {"dateTime": end, "timeZone": "America/Vancouver"}


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


def test_hidden_calendars_are_searched_too():
    service = fake_service(STUDY_PLANNER_ONLY)

    find_or_create_calendar(service)

    list_call = service.calendarList.return_value.list.call_args
    assert list_call.kwargs["showHidden"] is True


def test_missing_calendar_is_created_in_vancouver_time():
    service = fake_service([{"items": [{"id": "main", "summary": "Me"}]}])

    assert find_or_create_calendar(service) == "new-id"
    service.calendars.return_value.insert.assert_called_once_with(
        body={"summary": CALENDAR_NAME, "timeZone": "America/Vancouver"}
    )


# --- Creating and deleting events --------------------------------------------


@pytest.mark.parametrize("action", ["Intense", "Light", "Rest"])
def test_event_goes_into_the_study_planner_calendar(action):
    service = fake_service(STUDY_PLANNER_ONLY)

    create_event_for_action(action, DAY, service)

    kwargs = inserted_event(service)
    assert kwargs["calendarId"] == "sp"
    assert kwargs["body"] == build_event(action, DAY)


def test_created_event_is_returned():
    service = fake_service(STUDY_PLANNER_ONLY)
    created = {"id": "evt", "htmlLink": "https://calendar.google.com/event?eid=x"}
    service.events.return_value.insert.return_value.execute.return_value = created

    assert create_event_for_action("Light", DAY, service) == created


def test_bad_input_makes_no_api_calls():
    service = fake_service()
    with pytest.raises(ValueError):
        create_event_for_action("Nap", DAY, service)
    assert service.mock_calls == []


def test_bad_input_does_not_start_a_login(monkeypatch):
    def fail():
        raise AssertionError("get_service should not be called")

    monkeypatch.setattr(calendar_client, "get_service", fail)
    with pytest.raises(ValueError):
        create_event_for_action("Nap", DAY)


def test_saved_login_is_used_when_no_service_is_given(monkeypatch):
    service = fake_service(STUDY_PLANNER_ONLY)
    monkeypatch.setattr(calendar_client, "get_service", lambda: service)

    create_event_for_action("Rest", DAY)

    assert inserted_event(service)["calendarId"] == "sp"


def test_calendar_the_app_did_not_create_gives_a_clear_error():
    service = fake_service(STUDY_PLANNER_ONLY)
    insert = service.events.return_value.insert.return_value
    insert.execute.side_effect = http_error(403)

    with pytest.raises(PermissionError, match="Rename or delete that calendar"):
        create_event_for_action("Light", DAY, service)


def test_other_google_errors_are_not_hidden():
    service = fake_service(STUDY_PLANNER_ONLY)
    insert = service.events.return_value.insert.return_value
    insert.execute.side_effect = http_error(500)

    with pytest.raises(HttpError):
        create_event_for_action("Light", DAY, service)


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
    flow = MagicMock()
    browser_login = flow.from_client_secrets_file.return_value.run_local_server
    browser_login.return_value.to_json.return_value = '{"new": "login"}'
    monkeypatch.setattr(calendar_client, "InstalledAppFlow", flow)
    return SimpleNamespace(
        token_file=token_file, flow=flow, new_creds=browser_login.return_value
    )


def expired_login(monkeypatch, refresh_token="refresh"):
    """Make the saved login load as an expired one with the right permissions."""
    creds = MagicMock(valid=False, expired=True, refresh_token=refresh_token)
    creds.has_scopes.return_value = True
    loader = MagicMock()
    loader.from_authorized_user_file.return_value = creds
    monkeypatch.setattr(calendar_client, "Credentials", loader)
    return creds


def test_saved_login_with_the_right_permissions_is_reused(login):
    write_token(login.token_file, SCOPES)
    saved = login.token_file.read_text()

    calendar_client.get_credentials()

    login.flow.from_client_secrets_file.assert_not_called()
    assert login.token_file.read_text() == saved


@pytest.mark.parametrize(
    "old_scopes",
    [
        # The Stage 1.5 login, which cannot create the Study Planner calendar.
        ["https://www.googleapis.com/auth/calendar.events"],
        # Only one of the two permissions the app needs.
        [SCOPES[0]],
    ],
)
def test_saved_login_missing_a_permission_asks_to_log_in_again(login, old_scopes):
    write_token(login.token_file, old_scopes)

    creds = calendar_client.get_credentials()

    assert creds is login.new_creds
    assert login.flow.from_client_secrets_file.call_args.args[1] == SCOPES
    assert login.token_file.read_text() == '{"new": "login"}'


def test_first_run_opens_the_browser_login(login):
    assert calendar_client.get_credentials() is login.new_creds
    assert login.token_file.read_text() == '{"new": "login"}'


def test_expired_login_is_refreshed_without_the_browser(login, monkeypatch):
    login.token_file.write_text("{}")
    creds = expired_login(monkeypatch)

    def successful_refresh(request):
        creds.valid = True

    creds.refresh.side_effect = successful_refresh
    creds.to_json.return_value = '{"refreshed": true}'

    assert calendar_client.get_credentials() is creds
    login.flow.from_client_secrets_file.assert_not_called()
    assert login.token_file.read_text() == '{"refreshed": true}'


def test_revoked_or_old_login_asks_to_log_in_again(login, monkeypatch):
    # In Google's "Testing" mode a saved login stops working after 7 days.
    login.token_file.write_text("{}")
    creds = expired_login(monkeypatch)
    creds.refresh.side_effect = RefreshError("invalid_grant")

    assert calendar_client.get_credentials() is login.new_creds
    assert login.token_file.read_text() == '{"new": "login"}'


def test_login_without_a_refresh_token_opens_the_browser(login, monkeypatch):
    login.token_file.write_text("{}")
    creds = expired_login(monkeypatch, refresh_token=None)

    assert calendar_client.get_credentials() is login.new_creds
    creds.refresh.assert_not_called()
