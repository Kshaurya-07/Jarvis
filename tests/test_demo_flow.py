from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.demo_manager import demo_manager
from app.services.agent_service import AgentResponse, ToolExecutionRecord
from app.tools.notes_tools import create_note, search_notes
from app.tools.reminders_tools import reminders_storage
from app.tools.memory_tools import memory_storage


# --- 1. Local Demo Page Tests ---

def test_demo_page_served_and_fictional_content(client: TestClient):
    """Verify that the local demo page is served with rich fictional science content and no personal data."""
    # Test GET /demo/
    res = client.get("/demo/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    html = res.text

    # Verify fictional title and key elements
    assert "Deep Horizon: Exploring Europa's Subsurface Ocean" in html
    assert "Fictional Science Dossier" in html
    assert "id=\"demoSearchInput\"" in html
    assert "id=\"studyQuizHelp\"" in html
    assert "Deep-Ice Radar Sounder (DIRS)" in html
    assert "Sub-Plume Mass Spectrometer (SPMS)" in html

    # Verify safety and academic integrity notice
    assert "Non-Graded Study Aid" in html
    assert "Jarvis will <em>never</em> automatically select or submit quiz answers" in html

    # Verify no real personal data, accounts, or secrets exist in the demo HTML
    assert "password" not in html.lower() or "input type=\"password\"" not in html
    assert "@gmail.com" not in html
    assert "apikey" not in html.lower()

    # Test /demo redirect
    res_redirect = client.get("/demo", follow_redirects=False)
    assert res_redirect.status_code in (200, 301, 302, 307, 308)


# --- 2. Demo Status & Lifecycle Tests ---

def test_demo_status_api(client: TestClient):
    """Verify GET /api/demo/status returns accurate demo metadata, steps, and URL."""
    res = client.get("/api/demo/status")
    assert res.status_code == 200
    data = res.json()

    assert data["demo_version"] == "1.0"
    assert data["backend_connected"] is True
    assert data["demo_page_url"] == "http://127.0.0.1:8000/demo/"
    assert data["companion_url"] == "http://127.0.0.1:8000/mobile/"
    assert "steps" in data
    assert len(data["steps"]) >= 7
    assert data["steps"][0]["step"] == 1
    assert "Start Local Backend" in data["steps"][0]["title"]
    assert "safety_guarantee" in data


def test_demo_seed_and_reset_lifecycle_isolates_user_data(client: TestClient):
    """Verify that seed_demo_data creates [DEMO] items, and clear_demo_data wipes only demo items."""
    # 1. Create real user data first
    user_note_res = create_note(title="personal_work_plan", content="Real user work plan content.")
    assert user_note_res.success is True
    real_note_path = settings.NOTES_DIR / "personal_work_plan.md"
    assert real_note_path.exists()

    user_rem = reminders_storage.add(title="Buy anniversary gift", due_time="Tomorrow 5 PM")
    memory_storage.put("user_favorite_editor", "VS Code")

    # 2. Seed demo data
    res_seed = client.post("/api/demo/seed")
    assert res_seed.status_code == 200
    seed_data = res_seed.json()
    assert seed_data["status"] == "seeded"
    assert seed_data["seeded_items"]["notes"] == 1
    assert seed_data["seeded_items"]["reminders"] == 1
    assert seed_data["seeded_items"]["memories"] == 1

    # 3. Check demo status reflects seeded state
    res_status = client.get("/api/demo/status")
    status_data = res_status.json()
    assert status_data["active_demo_data"]["demo_notes_count"] >= 1
    assert status_data["active_demo_data"]["demo_reminders_count"] >= 1
    assert status_data["active_demo_data"]["demo_memories_count"] >= 1

    # Verify demo note exists on filesystem
    demo_note_path = settings.NOTES_DIR / "demo_europa_mission_notes.md"
    assert demo_note_path.exists()
    demo_content = demo_note_path.read_text(encoding="utf-8")
    assert "Europa Deep Horizon" in demo_content
    assert "[DEMO]" in demo_content

    # 4. Clear demo data
    res_reset = client.post("/api/demo/reset")
    assert res_reset.status_code == 200
    reset_data = res_reset.json()
    assert reset_data["status"] == "cleared"
    assert reset_data["deleted_items"]["notes"] >= 1
    assert reset_data["deleted_items"]["reminders"] >= 1
    assert reset_data["deleted_items"]["memories"] >= 1

    # 5. Verify demo items are removed
    assert not demo_note_path.exists()

    all_reminders = reminders_storage.list_all(include_completed=True)
    demo_reminders = [r for r in all_reminders if r.title.strip().upper().startswith("[DEMO]")]
    assert len(demo_reminders) == 0

    assert memory_storage.get("demo_favorite_mission") is None

    # 6. CRITICAL: Verify real user data was completely preserved!
    assert real_note_path.exists()
    assert "Real user work plan content" in real_note_path.read_text(encoding="utf-8")

    user_reminders = [r for r in all_reminders if r.title == "Buy anniversary gift"]
    assert len(user_reminders) == 1

    user_mem = memory_storage.get("user_favorite_editor")
    assert user_mem is not None
    assert user_mem.content == "VS Code"


# --- 3. End-to-End Companion Chat Flow ---

def test_e2e_companion_chat_command(client: TestClient):
    """Verify sending a text command from companion to the laptop agent executes safely."""
    mock_agent_response = AgentResponse(
        message="System status: Memory 38% utilized, Battery 92% (charging), Available storage 145 GB.",
        tools_executed=[
            ToolExecutionRecord(
                tool_name="get_system_status",
                arguments={},
                success=True,
                output={"battery": "92%", "memory": "38%", "storage": "145 GB"},
            )
        ],
        success=True,
    )

    with patch("app.api.routes.agent_service.chat", new=AsyncMock(return_value=mock_agent_response)):
        # Send system status query
        res = client.post("/api/chat", json={"message": "What is the system status?"})
        assert res.status_code == 200
        data = res.json()

        assert data["success"] is True
        assert "reply" in data
        assert "System status:" in data["reply"]
        assert len(data["tools_executed"]) == 1
        assert data["tools_executed"][0]["tool_name"] == "get_system_status"


# --- 4. End-to-End Chrome Extension Tab Inspection Flow ---

def test_e2e_extension_read_page_grounded_summary(client: TestClient):
    """Verify Chrome extension can inspect active tab text and receive grounded response with disclosure."""
    fictional_page_text = (
        "Project Deep Horizon is an autonomous scientific mission to Jupiter's moon Europa. "
        "Scheduled for launch in October 2032, it will deploy an autonomous cryobot capable of melting "
        "through 15 kilometers of surface ice to explore the subsurface liquid water ocean. "
        "Primary instruments include Deep-Ice Radar Sounder and Sub-Plume Mass Spectrometer."
    )

    mock_gemini_response = MagicMock()
    mock_gemini_response.text = (
        "Project Deep Horizon is an autonomous scientific mission to Europa scheduled to launch in October 2032. "
        "It uses a cryobot to penetrate 15 km of ice and carries Deep-Ice Radar."
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_gemini_response

    with patch("app.services.agent_service.agent_service._get_client", return_value=mock_client):
        res = client.post(
            "/api/extension/read-page",
            json={
                "url": "http://127.0.0.1:8000/demo/",
                "title": "Deep Horizon: Europa Mission Guide",
                "page_text": fictional_page_text,
                "question": "What is the launch date and how thick is the ice?",
                "mode": "summary",
            },
        )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["mode"] == "summary"
        assert "2032" in data["reply"]
        assert data["chars_processed"] == len(fictional_page_text)
        assert "Notice: Visible page text was transmitted" in data["disclosure"]


def test_e2e_extension_practice_quiz_help_mode(client: TestClient):
    """Verify non-graded practice quiz help explains questions without submitting answers."""
    quiz_page_text = (
        "Question 1: What is the primary function of the Deep-Ice Radar Sounder (DIRS)? "
        "Option A: Optical photography of surface fractures. "
        "Option B: Probing beneath the ice shell to detect the liquid water ocean boundary. "
        "Option C: Gravitational communication relay with Earth."
    )

    mock_gemini_response = MagicMock()
    mock_gemini_response.text = (
        "Regarding Question 1: Option B is correct because the Deep-Ice Radar Sounder uses radio sounding "
        "to penetrate the ice shell and detect dielectric discontinuities at the ocean boundary. "
        "(Remember: Jarvis does not complete or submit quizzes; select your answer manually)."
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_gemini_response

    with patch("app.services.agent_service.agent_service._get_client", return_value=mock_client):
        res = client.post(
            "/api/extension/read-page",
            json={
                "url": "http://127.0.0.1:8000/demo/",
                "title": "Europa Mission Study Quiz",
                "page_text": quiz_page_text,
                "question": "Which option is correct for Question 1 and why?",
                "mode": "quiz_help",
            },
        )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["mode"] == "quiz_help"
        assert "Option B" in data["reply"]
        assert "practice quiz" in data["disclosure"].lower() or "study" in data["disclosure"].lower()


# --- 5. Browser Automation Safe Field Filling on Demo Page ---

def test_e2e_demo_safe_field_fill_workflow(client: TestClient):
    """Verify safe non-sensitive field filling on the demo page with confirmation."""
    # 1. Plan field fill on local demo page
    res_plan = client.post(
        "/api/browser/plan-action",
        json={
            "action_type": "fill_field",
            "approved_domain": "127.0.0.1",
            "selector": "#demoSearchInput",
            "value": "subsurface thermal vents",
            "field_description": "Search input on Europa demo dossier",
        },
    )
    assert res_plan.status_code == 200
    plan_data = res_plan.json()
    assert plan_data["requires_confirmation"] is True
    conf_id = plan_data["confirmation_id"]
    assert conf_id is not None
    assert "Search input on Europa demo dossier" in plan_data["description"]
    assert plan_data["approved_domain"] == "127.0.0.1"

    # 2. Confirm the planned action
    res_conf = client.post(
        "/api/confirm",
        json={"confirmation_id": conf_id, "approve": True},
    )
    assert res_conf.status_code == 200
    conf_data = res_conf.json()
    assert conf_data["success"] is True
    assert "success" in conf_data["message"].lower()


def test_e2e_sensitive_field_fill_blocked_on_demo_page(client: TestClient):
    """Verify password and sensitive fields are strictly blocked even on approved local demo domain."""
    # Attempt to plan filling a password field
    res_plan = client.post(
        "/api/browser/plan-action",
        json={
            "action_type": "fill_field",
            "approved_domain": "127.0.0.1",
            "selector": "input[type='password']",
            "value": "mySecretPassword123!",
            "field_description": "Password field",
        },
    )
    assert res_plan.status_code == 400
    assert "refusal" in res_plan.json()["detail"].lower() or "sensitive" in res_plan.json()["detail"].lower()


# --- 6. Mobile Web UI Companion Static Serving Tests ---

def test_mobile_companion_serves_demo_tour_elements(client: TestClient):
    """Verify the mobile web companion serves the Phase 10 demo tour button and drawer."""
    res = client.get("/mobile/")
    assert res.status_code == 200
    html = res.text

    assert "id=\"nav-demo-btn\"" in html
    assert "Demo Tour" in html
    assert "id=\"demo-drawer\"" in html
    assert "id=\"seed-demo-btn\"" in html
    assert "id=\"reset-demo-btn\"" in html
    assert "Phase 10 Guided Demo" in html
