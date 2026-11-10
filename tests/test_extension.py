from unittest.mock import MagicMock, patch

from app.core.logger import action_logger
from app.tools.registry import tool_registry


def test_origin_validation_allowed_origins(client):
    # Localhost is allowed
    res1 = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res1.status_code == 200

    # 127.0.0.1 is allowed
    res2 = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert res2.status_code == 200

    # Chrome extension origin is allowed
    res3 = client.get("/health", headers={"Origin": "chrome-extension://abcdefghijklmnopqrstuvwxyz123456"})
    assert res3.status_code == 200


def test_origin_validation_rejects_unauthorized_origins(client):
    # External malicious domain blocked
    res1 = client.get("/health", headers={"Origin": "https://malicious-site.com"})
    assert res1.status_code == 403
    assert "not authorized" in res1.json()["detail"]

    # Remote origin blocked
    res2 = client.post(
        "/api/chat",
        headers={"Origin": "http://evil-tracker.org"},
        json={"message": "hello"},
    )
    assert res2.status_code == 403


def test_extension_request_size_limit_rejected(client):
    # Exceeds 50,000 characters limit
    oversized_text = "A" * 50001
    response = client.post(
        "/api/extension/read-page",
        json={
            "url": "https://example.com/practice-quiz",
            "title": "Practice Quiz",
            "page_text": oversized_text,
            "mode": "summary",
        },
    )
    assert response.status_code in [413, 422]


def test_extension_empty_page_text_rejected(client):
    response = client.post(
        "/api/extension/read-page",
        json={
            "url": "https://example.com/test",
            "title": "Empty Page",
            "page_text": "",
            "mode": "summary",
        },
    )
    assert response.status_code == 422


def test_extension_read_page_with_mocked_gemini(client):
    mock_gemini_response = MagicMock()
    mock_gemini_response.text = "This page discusses Python asynchronous programming concepts."

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_gemini_response

    with patch("app.services.agent_service.agent_service._get_client", return_value=mock_client):
        response = client.post(
            "/api/extension/read-page",
            json={
                "url": "https://docs.python.org/3/library/asyncio.html",
                "title": "asyncio docs",
                "page_text": "asyncio is a library to write concurrent code using the async/await syntax.",
                "question": "What is asyncio?",
                "mode": "summary",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Python asynchronous programming" in data["reply"]
        assert "Notice: Visible page text was transmitted" in data["disclosure"]
        assert data["chars_processed"] > 0


def test_extension_practice_quiz_help_mode(client):
    mock_gemini_response = MagicMock()
    mock_gemini_response.text = (
        "Practice Quiz Explanation: Question 1 tests Big-O complexity. "
        "Option A represents O(1) constant time, while Option B is O(n) linear time."
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_gemini_response

    with patch("app.services.agent_service.agent_service._get_client", return_value=mock_client):
        response = client.post(
            "/api/extension/read-page",
            json={
                "url": "https://example.edu/quiz/practice-1",
                "title": "Algorithms Practice",
                "page_text": "Question 1: What is the time complexity of array index lookup? A: O(1) B: O(n)",
                "question": "Can you compare Option A and Option B?",
                "mode": "quiz_help",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["mode"] == "quiz_help"
        assert "Option A represents O(1)" in data["reply"]


def test_extension_audit_log_never_stores_raw_page_text(client):
    initial_actions_count = len(action_logger.get_recent_actions())

    secret_page_text = "TOP_SECRET_CONTENT_THAT_MUST_NEVER_BE_LOGGED"
    mock_gemini_response = MagicMock()
    mock_gemini_response.text = "Grounded summary."

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_gemini_response

    with patch("app.services.agent_service.agent_service._get_client", return_value=mock_client):
        client.post(
            "/api/extension/read-page",
            json={
                "url": "https://secure.example.com/notes",
                "title": "Private Page",
                "page_text": secret_page_text,
                "mode": "summary",
            },
        )

    actions = action_logger.get_recent_actions()
    assert len(actions) > initial_actions_count
    last_action = actions[-1]
    assert last_action.tool_name == "extension_read_page"

    # Verify secret page text is not present anywhere in the audit log details
    assert secret_page_text not in (last_action.details or "")


def test_rule_no_quiz_click_or_submit_tool_exists():
    """
    CRITICAL SAFETY RULE:
    Jarvis must NOT have any tools that select answers, submit forms,
    or complete quizzes on behalf of the user.
    """
    registered_tools = tool_registry.get_all_tools()
    tool_names = [t.name.lower() for t in registered_tools]

    # Forbidden tool names and prefixes
    forbidden_terms = [
        "submit_quiz",
        "click_quiz",
        "submit_form",
        "click_answer",
        "auto_fill",
        "select_answer",
        "take_test",
        "complete_quiz",
    ]

    for name in tool_names:
        for forbidden in forbidden_terms:
            assert forbidden not in name, f"Forbidden automated quiz tool detected: {name}"

    # Only approved Phase 1-8 tools are registered
    approved_tools = {
        "list_files",
        "read_text_file",
        "create_note",
        "search_notes",
        "open_application",
        "get_battery_status",
        "get_storage_status",
        "get_memory_status",
        "capture_screenshot",
        "analyze_screenshot",
        "create_reminder",
        "list_reminders",
        "complete_reminder",
        "delete_reminder",
        "remember_item",
        "forget_item",
        "list_memories",
        "web_search",
        "get_daily_briefing",
        "list_gmail_messages",
        "summarize_gmail_messages",
        "list_calendar_events",
        "summarize_calendar_events",
        "browser_navigate",
        "browser_read_page",
        "browser_fill_field",
    }
    assert set(tool_names) == approved_tools
