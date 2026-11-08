import base64
import json
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import settings
from app.core.google_auth import google_auth_manager
from app.tools.registry import tool_registry
from app.tools.gmail_tools import list_gmail_messages, summarize_gmail_messages
from app.tools.calendar_tools import list_calendar_events, summarize_calendar_events
from app.tools.memory_tools import memory_storage


# --- Gmail Tests ---

def test_gmail_requires_connected_account():
    """Verify Gmail tools fail gracefully when Google account is not connected."""
    with patch.object(google_auth_manager, "is_connected", return_value=False):
        res_list = list_gmail_messages()
        assert res_list.success is False
        assert "Google account is not connected" in res_list.error
        assert "/api/auth/google/url" in res_list.error

        res_sum = summarize_gmail_messages()
        assert res_sum.success is False
        assert "Google account is not connected" in res_sum.error


def test_gmail_list_messages_mocked():
    """Verify list_gmail_messages extracts metadata without reading full bodies."""
    mock_service = MagicMock()
    mock_messages_resource = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages_resource

    # Mock list call
    mock_list_call = MagicMock()
    mock_list_call.execute.return_value = {
        "messages": [
            {"id": "msg_001", "threadId": "th_001"},
            {"id": "msg_002", "threadId": "th_002"},
        ]
    }
    mock_messages_resource.list.return_value = mock_list_call

    # Mock get call for metadata
    def mock_get(userId, id, format=None, metadataHeaders=None):
        call_obj = MagicMock()
        if id == "msg_001":
            call_obj.execute.return_value = {
                "id": "msg_001",
                "threadId": "th_001",
                "snippet": "Preview of first email...",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "alice@example.com"},
                        {"name": "Subject", "value": "Project Roadmap Review"},
                        {"name": "Date", "value": "Mon, 9 Nov 2026 09:00:00 +0000"},
                    ]
                },
            }
        else:
            call_obj.execute.return_value = {
                "id": "msg_002",
                "threadId": "th_002",
                "snippet": "Preview of second email...",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "bob@example.com"},
                        {"name": "Subject", "value": "Quarterly Budget"},
                        {"name": "Date", "value": "Mon, 9 Nov 2026 10:30:00 +0000"},
                    ]
                },
            }
        return call_obj

    mock_messages_resource.get.side_effect = mock_get

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.gmail_tools.build", return_value=mock_service):
                res = list_gmail_messages(max_results=5)
                assert res.success is True
                assert res.output["count"] == 2
                assert res.output["read_only"] is True

                first = res.output["messages"][0]
                assert first["id"] == "msg_001"
                assert first["sender"] == "alice@example.com"
                assert first["subject"] == "Project Roadmap Review"
                assert first["snippet"] == "Preview of first email..."


def test_gmail_summarize_messages_discloses_transmission():
    """Verify summarize_gmail_messages clearly tells user that email content is sent to Gemini."""
    mock_service = MagicMock()
    mock_messages_resource = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages_resource

    # Body encoded in base64 URL safe
    raw_body = "Hi team, please review the Q3 financials by end of day today."
    b64_data = base64.urlsafe_b64encode(raw_body.encode("utf-8")).decode("ascii")

    mock_get_call = MagicMock()
    mock_get_call.execute.return_value = {
        "id": "msg_fin_100",
        "payload": {
            "headers": [
                {"name": "From", "value": "finance@example.com"},
                {"name": "Subject", "value": "Urgent Financials Review"},
                {"name": "Date", "value": "Mon, 9 Nov 2026 11:00:00 +0000"},
            ],
            "body": {"data": b64_data},
            "mimeType": "text/plain",
        },
    }
    mock_messages_resource.get.return_value = mock_get_call

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.gmail_tools.build", return_value=mock_service):
                res = summarize_gmail_messages(message_ids=["msg_fin_100"])
                assert res.success is True
                assert res.output["count"] == 1
                # Must disclose external transmission to Gemini
                assert "transmitted to Google Gemini" in res.output["disclosure"]
                assert "summary" in res.output
                assert "analyzed_messages" in res.output


def test_gmail_never_logs_email_bodies_or_subjects():
    """
    CRITICAL PRIVACY TEST:
    Verify that executing Gmail tools does NOT log email bodies, subjects,
    or sender addresses to the action log.
    """
    mock_service = MagicMock()
    mock_messages_resource = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages_resource

    secret_subject = "CONFIDENTIAL_MERGER_DOC_7788"
    secret_sender = "secret_agent_99@classified.corp"
    secret_body = "The top-secret code is 987654321."
    b64_body = base64.urlsafe_b64encode(secret_body.encode("utf-8")).decode("ascii")

    mock_messages_resource.list.return_value.execute.return_value = {
        "messages": [{"id": "sec_001"}]
    }

    mock_messages_resource.get.return_value.execute.return_value = {
        "id": "sec_001",
        "snippet": "Classified preview snippet",
        "payload": {
            "headers": [
                {"name": "From", "value": secret_sender},
                {"name": "Subject", "value": secret_subject},
            ],
            "body": {"data": b64_body},
            "mimeType": "text/plain",
        },
    }

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.gmail_tools.build", return_value=mock_service):
                # Execute tools via registry
                tool_registry.execute_tool("list_gmail_messages", {"max_results": 1})
                tool_registry.execute_tool("summarize_gmail_messages", {"message_ids": ["sec_001"]})

    # Read action log
    log_content = ""
    if settings.ACTION_LOG_FILE.exists():
        log_content = settings.ACTION_LOG_FILE.read_text(encoding="utf-8")

    assert secret_subject not in log_content, "Email subject leaked into action log!"
    assert secret_sender not in log_content, "Sender address leaked into action log!"
    assert secret_body not in log_content, "Email body leaked into action log!"


def test_gmail_never_stores_body_in_persistent_memory():
    """Verify that summarizing or listing emails does NOT silently populate local memories."""
    initial_count = len(memory_storage.list_all())

    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {"messages": []}

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.gmail_tools.build", return_value=mock_service):
                list_gmail_messages()
                summarize_gmail_messages()

    assert len(memory_storage.list_all()) == initial_count


# --- Calendar Tests ---

def test_calendar_requires_connected_account():
    """Verify Calendar tools fail gracefully when Google account is not connected."""
    with patch.object(google_auth_manager, "is_connected", return_value=False):
        res_list = list_calendar_events()
        assert res_list.success is False
        assert "Google account is not connected" in res_list.error
        assert "/api/auth/google/url" in res_list.error

        res_sum = summarize_calendar_events()
        assert res_sum.success is False
        assert "Google account is not connected" in res_sum.error


def test_calendar_date_validation():
    """Verify date range validation on calendar tools."""
    with patch.object(google_auth_manager, "is_connected", return_value=True):
        # Invalid date format
        res_inv = list_calendar_events(time_min="invalid-date-string")
        assert res_inv.success is False
        assert "Invalid ISO 8601 date string" in res_inv.error

        # time_min > time_max
        res_reversed = list_calendar_events(
            time_min="2026-11-20T00:00:00Z",
            time_max="2026-11-10T00:00:00Z",
        )
        assert res_reversed.success is False
        assert "time_min must be earlier than or equal to time_max" in res_reversed.error

        # Range > 365 days
        res_over = list_calendar_events(
            time_min="2026-01-01T00:00:00Z",
            time_max="2027-06-01T00:00:00Z",
        )
        assert res_over.success is False
        assert "exceeds the maximum allowed window of 365 days" in res_over.error


def test_calendar_list_events_mocked():
    """Verify list_calendar_events parses event details correctly."""
    mock_service = MagicMock()
    mock_events_resource = MagicMock()
    mock_service.events.return_value = mock_events_resource

    mock_events_resource.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt_001",
                "summary": "Team Sync Meeting",
                "start": {"dateTime": "2026-11-10T10:00:00Z"},
                "end": {"dateTime": "2026-11-10T11:00:00Z"},
                "location": "Room 402 / Google Meet",
                "status": "confirmed",
                "htmlLink": "https://calendar.google.com/event?eid=001",
            },
            {
                "id": "evt_002",
                "summary": "Doctor Appointment",
                "start": {"dateTime": "2026-11-11T14:30:00Z"},
                "end": {"dateTime": "2026-11-11T15:30:00Z"},
                "location": "Medical Center",
                "status": "confirmed",
                "htmlLink": "https://calendar.google.com/event?eid=002",
            },
        ]
    }

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.calendar_tools.build", return_value=mock_service):
                res = list_calendar_events(
                    time_min="2026-11-09T00:00:00Z",
                    time_max="2026-11-15T00:00:00Z",
                )
                assert res.success is True
                assert res.output["count"] == 2
                assert res.output["read_only"] is True

                first = res.output["events"][0]
                assert first["id"] == "evt_001"
                assert first["summary"] == "Team Sync Meeting"
                assert first["start"] == "2026-11-10T10:00:00Z"
                assert first["location"] == "Room 402 / Google Meet"


def test_calendar_summarize_events_discloses_transmission():
    """Verify summarize_calendar_events discloses transmission to Gemini."""
    mock_service = MagicMock()
    mock_events_resource = MagicMock()
    mock_service.events.return_value = mock_events_resource

    mock_events_resource.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt_brief_1",
                "summary": "Sprint Planning",
                "start": {"dateTime": "2026-11-10T09:00:00Z"},
                "end": {"dateTime": "2026-11-10T10:30:00Z"},
                "location": "Online",
            }
        ]
    }

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.calendar_tools.build", return_value=mock_service):
                res = summarize_calendar_events(time_min="2026-11-10T00:00:00Z")
                assert res.success is True
                assert res.output["count"] == 1
                assert "transmitted to Google Gemini" in res.output["disclosure"]
                assert "summary" in res.output


def test_calendar_never_logs_event_titles_or_locations():
    """
    CRITICAL PRIVACY TEST:
    Verify that executing Calendar tools does NOT log event titles,
    descriptions, or locations into the audit action log.
    """
    mock_service = MagicMock()
    mock_events_resource = MagicMock()
    mock_service.events.return_value = mock_events_resource

    secret_summary = "SECRET_CEO_BRIEFING_9911"
    secret_loc = "BUNKER_ROOM_ALPHA_77"

    mock_events_resource.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "sec_evt_1",
                "summary": secret_summary,
                "start": {"dateTime": "2026-11-12T10:00:00Z"},
                "end": {"dateTime": "2026-11-12T11:00:00Z"},
                "location": secret_loc,
            }
        ]
    }

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.calendar_tools.build", return_value=mock_service):
                tool_registry.execute_tool("list_calendar_events", {"time_min": "2026-11-12T00:00:00Z"})
                tool_registry.execute_tool("summarize_calendar_events", {"time_min": "2026-11-12T00:00:00Z"})

    log_content = ""
    if settings.ACTION_LOG_FILE.exists():
        log_content = settings.ACTION_LOG_FILE.read_text(encoding="utf-8")

    assert secret_summary not in log_content, "Event summary leaked into action log!"
    assert secret_loc not in log_content, "Event location leaked into action log!"


def test_calendar_never_stores_events_in_persistent_memory():
    """Verify that listing or summarizing calendar events does NOT silently alter memories."""
    initial_count = len(memory_storage.list_all())

    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.return_value = {"items": []}

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.calendar_tools.build", return_value=mock_service):
                list_calendar_events()
                summarize_calendar_events()

    assert len(memory_storage.list_all()) == initial_count


# --- Scope & Safety Validation ---

def test_strict_read_only_scopes_enforced():
    """Verify that only read-only scopes are requested for Google OAuth."""
    scopes = settings.GOOGLE_OAUTH_SCOPES
    assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
    assert "https://www.googleapis.com/auth/calendar.readonly" in scopes

    forbidden_scopes = [
        "gmail.send",
        "gmail.compose",
        "gmail.modify",
        "mail.google.com",
        "calendar.events",
    ]
    for s in scopes:
        for f in forbidden_scopes:
            assert f not in s, f"Forbidden non-read-only scope detected: {s}"


def test_no_write_tools_registered_for_gmail_or_calendar():
    """Verify that no tools exist that could create, modify, send, or delete emails or events."""
    all_tools = [t.name.lower() for t in tool_registry.get_all_tools()]
    forbidden = [
        "send_email",
        "send_gmail",
        "create_email",
        "delete_email",
        "delete_gmail",
        "trash_email",
        "archive_email",
        "mark_read",
        "create_event",
        "update_event",
        "delete_event",
        "edit_event",
        "modify_event",
    ]
    for t in all_tools:
        for f in forbidden:
            assert f not in t, f"Forbidden write tool detected: {t}"


# --- API Routes Tests ---

def test_gmail_and_calendar_api_routes(client):
    """Verify /api/gmail/* and /api/calendar/* HTTP endpoints."""
    # When not connected, returns 400
    with patch.object(google_auth_manager, "is_connected", return_value=False):
        res_g = client.get("/api/gmail/messages")
        assert res_g.status_code == 400

        res_c = client.get("/api/calendar/events")
        assert res_c.status_code == 400

    # When connected, returns expected response structures
    mock_service_gmail = MagicMock()
    mock_service_gmail.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": []
    }

    mock_service_cal = MagicMock()
    mock_service_cal.events.return_value.list.return_value.execute.return_value = {
        "items": []
    }

    with patch.object(google_auth_manager, "is_connected", return_value=True):
        with patch.object(google_auth_manager, "get_credentials", return_value=MagicMock()):
            with patch("app.tools.gmail_tools.build", return_value=mock_service_gmail):
                res_g_ok = client.get("/api/gmail/messages?max_results=5")
                assert res_g_ok.status_code == 200
                data_g = res_g_ok.json()
                assert "messages" in data_g
                assert data_g["read_only"] is True

            with patch("app.tools.calendar_tools.build", return_value=mock_service_cal):
                res_c_ok = client.get("/api/calendar/events?max_results=5")
                assert res_c_ok.status_code == 200
                data_c = res_c_ok.json()
                assert "events" in data_c
                assert data_c["read_only"] is True
