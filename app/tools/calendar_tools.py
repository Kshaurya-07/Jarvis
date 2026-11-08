import datetime
from typing import Any, Dict, List, Optional
from googleapiclient.discovery import build

from app.core.config import settings
from app.core.google_auth import (
    google_auth_manager,
    GoogleAuthRequiredError,
    GoogleTokenRevokedError,
)
from app.core.logger import app_logger
from app.tools.base import ToolResult


def _parse_iso_datetime(dt_str: Optional[str], default: datetime.datetime) -> datetime.datetime:
    """Parse an ISO 8601 string or return default datetime."""
    if not dt_str:
        return default
    # Replace trailing 'Z' with '+00:00' for standard python datetime parsing
    clean = dt_str.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    except ValueError as e:
        raise ValueError(f"Invalid ISO 8601 date string '{dt_str}': {e}") from e


def list_calendar_events(
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 10,
    calendar_id: str = "primary",
) -> ToolResult:
    """
    Read-only tool to list upcoming Google Calendar events within a specified date range.
    Strictly read-only: does not create, update, or delete calendar events.
    """
    if not google_auth_manager.is_connected():
        return ToolResult(
            success=False,
            error=(
                "Google account is not connected. Please connect your Google account "
                "via /api/auth/google/url to enable Google Calendar tools."
            ),
        )

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    try:
        dt_start = _parse_iso_datetime(time_min, now_utc)
        default_end = dt_start + datetime.timedelta(days=7)
        dt_end = _parse_iso_datetime(time_max, default_end)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))

    if dt_start > dt_end:
        return ToolResult(success=False, error="Invalid date range: time_min must be earlier than or equal to time_max.")

    if (dt_end - dt_start).days > 365:
        return ToolResult(success=False, error="Requested date range exceeds the maximum allowed window of 365 days.")

    max_results = max(1, min(int(max_results), settings.MAX_CALENDAR_RESULTS))

    try:
        creds = google_auth_manager.get_credentials()
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=dt_start.isoformat(),
            timeMax=dt_end.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        raw_items = events_result.get("items", [])
        events = []
        for it in raw_items:
            start_info = it.get("start", {})
            end_info = it.get("end", {})
            events.append({
                "id": it.get("id"),
                "summary": it.get("summary", "(No Title)"),
                "start": start_info.get("dateTime") or start_info.get("date"),
                "end": end_info.get("dateTime") or end_info.get("date"),
                "location": it.get("location"),
                "status": it.get("status"),
                "html_link": it.get("htmlLink"),
            })

        return ToolResult(
            success=True,
            output={
                "count": len(events),
                "events": events,
                "time_min": dt_start.isoformat(),
                "time_max": dt_end.isoformat(),
                "read_only": True,
            },
        )

    except (GoogleAuthRequiredError, GoogleTokenRevokedError) as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        app_logger.warning("Calendar API list_events error: %s", e)
        return ToolResult(success=False, error=f"Google Calendar API error: {str(e)}")


def summarize_calendar_events(
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    calendar_id: str = "primary",
) -> ToolResult:
    """
    Read-only tool to summarize Google Calendar events across a date range using Gemini.
    Explicitly discloses that calendar details are transmitted to Gemini for summarization.
    Does not store event titles, descriptions, or attendees in persistent memory or audit logs.
    """
    if not google_auth_manager.is_connected():
        return ToolResult(
            success=False,
            error="Google account is not connected. Please connect via /api/auth/google/url.",
        )

    list_res = list_calendar_events(
        time_min=time_min,
        time_max=time_max,
        max_results=settings.MAX_CALENDAR_RESULTS,
        calendar_id=calendar_id,
    )
    if not list_res.success:
        return list_res

    events = list_res.output.get("events", [])
    disclosure = "Notice: Calendar event details for this date range are being transmitted to Google Gemini for summarization."

    if not events:
        return ToolResult(
            success=True,
            output={
                "count": 0,
                "summary": "You have no upcoming calendar events in the selected date range.",
                "disclosure": disclosure,
                "time_min": list_res.output.get("time_min"),
                "time_max": list_res.output.get("time_max"),
                "read_only": True,
            },
        )

    summary_text = _generate_calendar_gemini_summary(events)

    return ToolResult(
        success=True,
        output={
            "count": len(events),
            "summary": summary_text,
            "events_count": len(events),
            "disclosure": disclosure,
            "time_min": list_res.output.get("time_min"),
            "time_max": list_res.output.get("time_max"),
            "read_only": True,
        },
    )


def _generate_calendar_gemini_summary(events: List[Dict[str, Any]]) -> str:
    """Generate a clean schedule overview using Gemini, with a deterministic fallback."""
    if not settings.GEMINI_API_KEY:
        lines = ["Upcoming Schedule Overview:"]
        for ev in events:
            loc = f" at {ev['location']}" if ev.get("location") else ""
            lines.append(f"- {ev['summary']} ({ev['start']} to {ev['end']}){loc}")
        return "\n".join(lines)

    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        formatted_events = []
        for idx, ev in enumerate(events, 1):
            formatted_events.append(
                f"[Event {idx}]\n"
                f"Title: {ev['summary']}\n"
                f"Start: {ev['start']}\n"
                f"End: {ev['end']}\n"
                f"Location: {ev.get('location') or 'None'}\n"
            )

        prompt = (
            "You are Jarvis, a personal assistant. Provide a structured and helpful summary of the following "
            "calendar events. Highlight key commitments, busy periods, potential conflicts, and travel/locations.\n\n"
            "=== CALENDAR EVENTS ===\n" + "\n---\n".join(formatted_events)
        )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip() if response.text else "No summary generated."
    except Exception as e:
        app_logger.warning("Gemini calendar summarization failed: %s", e)
        return f"Found {len(events)} events scheduled: " + ", ".join(f"'{ev['summary']}'" for ev in events)
