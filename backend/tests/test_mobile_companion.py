from unittest.mock import patch, AsyncMock

from app.core.config import settings
from app.services.agent_service import AgentResponse, ToolExecutionRecord


def test_mobile_companion_served(client):
    """Verify the mobile web app HTML is served with proper PWA and mobile tags."""
    res = client.get("/mobile/")
    assert res.status_code == 200
    html = res.text

    # Mobile viewport tag
    assert 'meta name="viewport"' in html
    assert "width=device-width" in html

    # Title & PWA manifest link
    assert "Jarvis Companion" in html
    assert 'rel="manifest" href="manifest.webmanifest"' in html

    # Essential UI elements
    assert 'id="connection-pill"' in html
    assert 'id="command-input"' in html
    assert 'id="send-btn"' in html
    assert 'id="stop-btn"' in html
    assert 'id="chat-stream"' in html
    assert 'id="actions-drawer"' in html
    assert 'id="settings-drawer"' in html
    assert 'id="voice-btn"' in html


def test_mobile_manifest_served(client):
    """Verify PWA manifest is served with correct JSON metadata."""
    res = client.get("/mobile/manifest.webmanifest")
    assert res.status_code == 200
    manifest = res.json()

    assert manifest["name"] == "Jarvis Mobile Companion"
    assert manifest["short_name"] == "Jarvis"
    assert manifest["display"] == "standalone"
    assert len(manifest["icons"]) >= 2
    assert any(i["sizes"] == "192x192" for i in manifest["icons"])
    assert any(i["sizes"] == "512x512" for i in manifest["icons"])


def test_mobile_service_worker_served(client):
    """Verify service worker script is served with cache rules."""
    res = client.get("/mobile/service-worker.js")
    assert res.status_code == 200
    sw_code = res.text

    # Caches app shell
    assert "jarvis-mobile-v1" in sw_code
    assert "manifest.webmanifest" in sw_code

    # Live network for API routes
    assert 'url.pathname.startsWith("/api")' in sw_code
    assert 'url.pathname.startsWith("/health")' in sw_code


def test_mobile_css_responsive_design(client):
    """Verify mobile CSS includes responsive breakpoints and touch target sizing."""
    res = client.get("/mobile/style.css")
    assert res.status_code == 200
    css = res.text

    # Touch-target sizing (48px standard)
    assert "--touch-target: 48px" in css or "48px" in css

    # Responsive media query for mobile/tablet
    assert "@media" in css
    assert "max-width: 480px" in css

    # Safe area insets for mobile gesture bars & notches
    assert "safe-area-inset-bottom" in css


def test_mobile_js_functionality_and_stop_control(client):
    """Verify mobile app script implements AbortController and privacy controls."""
    res = client.get("/mobile/app.js")
    assert res.status_code == 200
    js = res.text

    # AbortController for Stop / Pause control
    assert "AbortController" in js
    assert "activeAbortController.abort()" in js

    # Push-to-Talk voice integration
    assert "SpeechRecognition" in js or "webkitSpeechRecognition" in js

    # Command History privacy control (opt-in by default)
    assert "jarvis_history_opt_in" in js
    assert "jarvis_command_history" in js
    assert "localStorage" in js

    # Confirmation flow integration
    assert "/api/confirm" in js


def test_landing_root_redirect(client):
    """Verify root / redirects to the landing page (the homepage)."""
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/landing/"


def test_companion_alias_redirect(client):
    """Verify /companion/ redirects to the mobile companion interface."""
    res = client.get("/companion", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/mobile/"


def test_mobile_network_option_b_guard(client):
    """
    SECURITY CHECK (cloud-first):
    Local dev still binds localhost by default, but the Companion's main
    path is now cloud sign-in — the old "Localhost-Only mode (Option B)"
    copy was replaced. Tailscale pairing survives only as a labelled
    legacy section, not the main path.
    """
    assert settings.HOST == "127.0.0.1"

    res = client.get("/mobile/")
    assert res.status_code == 200
    # Cloud sign-in is the main path offered by the UI.
    assert "Sign in with Google" in res.text
    assert "Localhost-Only mode (Option B)" not in res.text
    # Tailscale is still present, but explicitly labelled legacy.
    assert "Legacy: laptop pairing (Tailscale)" in res.text


def test_mobile_command_history_privacy_controls(client):
    """Verify the UI includes clear command history toggle and deletion controls."""
    res = client.get("/mobile/")
    assert res.status_code == 200
    html = res.text

    # Opt-in toggle is present
    assert 'id="opt-in-history-toggle"' in html
    # Clear history button is present
    assert 'id="clear-history-btn"' in html
    # Discloses that passwords/keys are never stored
    assert "Never stores credentials, keys, or passwords" in html


def test_mobile_actions_feed_endpoint(client):
    """Verify recent actions feed provides non-sensitive audit logs for mobile drawer."""
    res = client.get("/api/actions?limit=10")
    assert res.status_code == 200
    actions = res.json()
    assert isinstance(actions, list)
    for act in actions:
        assert "tool_name" in act
        assert "status" in act
        assert "timestamp" in act


def test_mobile_chat_api_interaction(client):
    """Verify /api/chat behaves as expected when consumed by mobile companion."""
    mock_agent_response = AgentResponse(
        message="I found 2 files in your workspace.",
        tools_executed=[
            ToolExecutionRecord(
                tool_name="list_files",
                arguments={"subfolder": ""},
                success=True,
                output={"count": 2, "items": ["notes.txt", "tasks.txt"]},
            )
        ],
        success=True,
    )

    with patch("app.api.routes.agent_service.chat", new=AsyncMock(return_value=mock_agent_response)):
        res = client.post("/api/chat", json={"message": "List my workspace files"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["reply"] == "I found 2 files in your workspace."
        assert len(data["tools_executed"]) == 1
        assert data["tools_executed"][0]["tool_name"] == "list_files"

        assert data["tools_executed"][0]["tool_name"] == "list_files"


def test_companion_chat_shows_friendly_message_on_504():
    """A Vercel gateway timeout (HTTP 504) on chat must show the friendly
    message in the Companion, never a raw 'Server returned HTTP 504'
    (live bug, 2026-11-11: a slow chat showed the raw 504 in chat)."""
    from pathlib import Path

    app_js = (Path(__file__).resolve().parents[2] / "frontend" / "mobile" / "app.js").read_text()
    assert "That took too long — please try again." in app_js
    assert "response.status === 504" in app_js
    # A fetch that never gets a response maps to the same friendly message.
    assert 'err.name === "TypeError"' in app_js
