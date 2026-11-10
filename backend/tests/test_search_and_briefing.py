import asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.tools.reminders_tools import create_reminder
from app.tools.notes_tools import create_note
from app.tools.registry import tool_registry
from app.tools.search_tools import execute_web_search
from app.tools.briefing_tools import build_daily_briefing


# --- Web Search Tests ---

def test_search_requires_non_empty_query():
    res = asyncio.run(execute_web_search(query=""))
    assert res.success is False
    assert "Search query is required" in res.error


def test_search_enforces_query_length_cap():
    oversized = "python " * 50  # > 200 chars
    res = asyncio.run(execute_web_search(query=oversized))
    assert res.success is False
    assert "exceeds maximum allowed length" in res.error


def test_search_personal_data_safeguard_blocks_passwords():
    # Passwords in query blocked
    res = asyncio.run(execute_web_search(query="my password is: SuperSecret123!"))
    assert res.success is False
    assert "Privacy refusal" in res.error
    assert "prohibits transmitting passwords" in res.error


def test_search_personal_data_safeguard_blocks_api_keys():
    # API key in query blocked
    res = asyncio.run(execute_web_search(query="search for api_key = 'TEST-FAKE-KEY-1234567890'"))
    assert res.success is False
    assert "Privacy refusal" in res.error


def test_search_handles_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "SEARCH_API_KEY", None)
    res = asyncio.run(execute_web_search(query="Python release dates"))
    assert res.success is False
    assert "SEARCH_API_KEY" in res.error


def test_search_tavily_mocked_success(monkeypatch):
    monkeypatch.setattr(settings, "SEARCH_API_KEY", "test_key")
    monkeypatch.setattr(settings, "SEARCH_PROVIDER", "tavily")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "title": "Python 3.12 Release",
                "url": "https://www.python.org/downloads/release/python-3120/",
                "content": "Python 3.12 is the newest major release.",
                "published_date": "2023-10-02",
            },
            {
                "title": "FastAPI Framework",
                "url": "https://fastapi.tiangolo.com/",
                "content": "FastAPI is a modern web framework.",
                "published_date": "2024-01-15",
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        res = asyncio.run(execute_web_search(query="Python FastAPI news", max_results=2))
        assert res.success is True
        assert res.output["count"] == 2
        first = res.output["results"][0]
        assert first["title"] == "Python 3.12 Release"
        assert first["link"] == "https://www.python.org/downloads/release/python-3120/"
        assert first["source"] == "www.python.org"
        assert "cite links in markdown format" in res.output["instruction_for_assistant"]


def test_search_handles_timeout(monkeypatch):
    monkeypatch.setattr(settings, "SEARCH_API_KEY", "test_key")

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timed out")):
        res = asyncio.run(execute_web_search(query="Test timeout"))
        assert res.success is False
        assert "timed out" in res.error.lower()


def test_search_handles_rate_limit_429(monkeypatch):
    monkeypatch.setattr(settings, "SEARCH_API_KEY", "test_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    err = httpx.HTTPStatusError("Too Many Requests", request=MagicMock(), response=mock_resp)

    with patch("httpx.AsyncClient.post", side_effect=err):
        res = asyncio.run(execute_web_search(query="Test 429"))
        assert res.success is False
        assert "rate limit reached (HTTP 429)" in res.error


# --- Daily Briefing Tests ---

def test_daily_briefing_compilation_local_only():
    create_reminder(title="Submit Project Report", due_time="Today at 5 PM", notes="Include metrics")
    create_note(title="Weekly Sprint", content="# Tasks\n- [ ] Review PRs\n- [ ] Update docs")

    res = asyncio.run(build_daily_briefing(include_web_summary=False))
    assert res.success is True
    output = res.output
    assert output["briefing_type"] == "On-Demand Daily Briefing"
    assert output["on_demand"] is True

    # Check local reminders section
    reminders = output["local_reminders"]
    assert reminders["count"] >= 1
    assert "reminders" in reminders["source"]
    assert any("Submit Project Report" in item["title"] for item in reminders["items"])

    # Check local notes section
    notes = output["local_notes"]
    assert notes["count"] >= 1
    assert "notes" in notes["source"]

    # Web overview is None because include_web_summary was False
    assert output["web_overview"] is None


def test_daily_briefing_with_web_summary_mocked(monkeypatch):
    monkeypatch.setattr(settings, "SEARCH_API_KEY", "test_key")

    mock_search_res = MagicMock()
    mock_search_res.success = True
    mock_search_res.output = {
        "count": 1,
        "results": [
            {
                "title": "Local Tech News",
                "link": "https://news.example.com/tech",
                "source": "news.example.com",
                "snippet": "New AI models released.",
            }
        ],
    }

    with patch("app.tools.briefing_tools.execute_web_search", new_callable=AsyncMock, return_value=mock_search_res) as mock_search:
        res = asyncio.run(build_daily_briefing(
            include_web_summary=True,
            web_topics="latest tech news",
        ))
        assert res.success is True
        assert res.output["web_overview"] is not None
        assert res.output["web_overview"]["topic_query"] == "latest tech news"
        assert len(res.output["web_overview"]["results"]) == 1

        # Verify only the general user topic was searched, NOT private reminder/note text!
        mock_search.assert_called_once_with(query="latest tech news", max_results=3)


def test_briefing_api_endpoint(client):
    res = client.get("/api/briefing?include_web_summary=false")
    assert res.status_code == 200
    data = res.json()
    assert "local_reminders" in data
    assert "local_notes" in data
    assert "Attribution:" in data["attribution"]


def test_rule_no_write_gmail_or_calendar_tools():
    """Verify that only read-only Gmail and Calendar tools exist (no send, delete, create, or update)."""
    all_tools = [t.name.lower() for t in tool_registry.get_all_tools()]
    forbidden_write = [
        "send_gmail",
        "send_email",
        "delete_gmail",
        "delete_email",
        "archive_email",
        "trash_email",
        "mark_read",
        "create_event",
        "update_event",
        "delete_event",
        "edit_event",
    ]
    for t in all_tools:
        for f in forbidden_write:
            assert f not in t, f"Forbidden write tool detected: {t}"
