import time
from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.remote_auth import remote_session_manager
from app.main import app, is_allowed_host

PROD_ORIGIN = "https://jarvis-kumar-shaurya.vercel.app"
PREVIEW_ORIGIN = "https://jarvis-eta-ten-83.vercel.app"


@pytest.fixture(autouse=True)
def clean_remote_sessions():
    """Reset in-memory sessions and pairing rate limits before each test."""
    remote_session_manager._pairing_codes.clear()
    remote_session_manager._sessions.clear()
    remote_session_manager._pairing_failures.clear()
    yield
    remote_session_manager._pairing_codes.clear()
    remote_session_manager._sessions.clear()
    remote_session_manager._pairing_failures.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_pairing_code_generation_local_only(client: TestClient):
    """Pairing code generation must succeed on localhost and be rejected from remote origins."""
    # 1. Local generate succeeds
    resp = client.post("/api/remote/pair/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert "pairing_code" in data
    assert len(data["pairing_code"]) == 6
    assert data["pairing_code"].isdigit()
    assert data["expires_in_seconds"] == settings.REMOTE_PAIRING_CODE_TIMEOUT_SECONDS

    # 2. Remote origin cannot generate pairing codes (Must be generated on physical laptop)
    remote_resp = client.post(
        "/api/remote/pair/generate",
        headers={"Origin": PROD_ORIGIN}
    )
    assert remote_resp.status_code == 403
    assert "Pairing codes can only be generated directly on the local laptop" in remote_resp.json()["detail"]


def test_pairing_code_exchange_lifecycle(client: TestClient):
    """A valid code can be exchanged once for an in-memory session token, but cannot be reused."""
    # Generate code
    gen_resp = client.post("/api/remote/pair/generate")
    code = gen_resp.json()["pairing_code"]

    # Exchange code for token
    exchange_resp = client.post(
        "/api/remote/pair/exchange",
        json={"pairing_code": code},
        headers={"Origin": PROD_ORIGIN}
    )
    assert exchange_resp.status_code == 200
    ex_data = exchange_resp.json()
    token = ex_data["session_token"]
    assert token
    assert ex_data["token_type"] == "Bearer"
    assert ex_data["expires_in_seconds"] > 0

    # Code cannot be reused (one-time use)
    reuse_resp = client.post(
        "/api/remote/pair/exchange",
        json={"pairing_code": code},
        headers={"Origin": PROD_ORIGIN}
    )
    assert reuse_resp.status_code == 400
    assert "already been used" in reuse_resp.json()["detail"]


def test_pairing_code_expiry(client: TestClient):
    """Expired pairing codes must be rejected."""
    code = remote_session_manager.generate_pairing_code()
    # Artificially expire the code
    info = remote_session_manager._pairing_codes[code]
    info.expires_at = time.time() - 10

    resp = client.post(
        "/api/remote/pair/exchange",
        json={"pairing_code": code},
        headers={"Origin": PROD_ORIGIN}
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_pairing_brute_force_rate_limit(client: TestClient):
    """More than 5 failed pairing attempts within the rate limit window must be blocked with HTTP 429."""
    for i in range(settings.PAIRING_RATE_LIMIT):
        bad_resp = client.post(
            "/api/remote/pair/exchange",
            json={"pairing_code": f"99990{i}"},
            headers={"Origin": PROD_ORIGIN}
        )
        assert bad_resp.status_code == 400

    # 6th attempt should be blocked by rate limiter
    blocked_resp = client.post(
        "/api/remote/pair/exchange",
        json={"pairing_code": "999906"},
        headers={"Origin": PROD_ORIGIN}
    )
    assert blocked_resp.status_code == 429
    assert "Too many failed pairing attempts" in blocked_resp.json()["detail"]
    assert "Retry-After" in blocked_resp.headers


def test_session_token_validation_and_status(client: TestClient):
    """Test checking token status and expiry."""
    # No token
    resp = client.get("/api/remote/session/status")
    assert resp.status_code == 200
    assert resp.json()["valid"] is False

    # Valid token
    code = remote_session_manager.generate_pairing_code()
    session = remote_session_manager.exchange_pairing_code(code, "127.0.0.1")

    valid_resp = client.get(
        "/api/remote/session/status",
        headers={"Authorization": f"Bearer {session.token}"}
    )
    assert valid_resp.status_code == 200
    assert valid_resp.json()["valid"] is True
    assert valid_resp.json()["expires_in_seconds"] > 0

    # Expired token
    session.expires_at = time.time() - 5
    exp_resp = client.get(
        "/api/remote/session/status",
        headers={"Authorization": f"Bearer {session.token}"}
    )
    assert exp_resp.status_code == 200
    assert exp_resp.json()["valid"] is False
    assert "expired" in exp_resp.json()["detail"]


def test_session_revocation_disconnect(client: TestClient):
    """Revoking a session immediately disables access."""
    code = remote_session_manager.generate_pairing_code()
    session = remote_session_manager.exchange_pairing_code(code, "127.0.0.1")

    # Revoke session
    revoke_resp = client.post(
        "/api/remote/session/revoke",
        headers={"Authorization": f"Bearer {session.token}"}
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked"] is True

    # Token is now revoked
    status_resp = client.get(
        "/api/remote/session/status",
        headers={"Authorization": f"Bearer {session.token}"}
    )
    assert status_resp.json()["valid"] is False
    assert "revoked" in status_resp.json()["detail"]


def test_remote_origin_requires_session_token(client: TestClient, monkeypatch):
    """Remote requests from the Vercel PWA must provide a valid session token."""
    # 1. Calling /api/chat from remote origin without session token -> 401
    unauth_resp = client.post(
        "/api/chat",
        json={"message": "System status"},
        headers={"Origin": PROD_ORIGIN}
    )
    assert unauth_resp.status_code == 401
    assert "Sign-in required" in unauth_resp.json()["detail"]

    # 2. Calling with invalid token -> 401
    bad_token_resp = client.post(
        "/api/chat",
        json={"message": "System status"},
        headers={
            "Origin": PROD_ORIGIN,
            "Authorization": "Bearer invalid_token_12345"
        }
    )
    assert bad_token_resp.status_code == 401
    assert "Remote authentication failed" in bad_token_resp.json()["detail"]

    # 3. Calling with valid session token -> Succeeds
    code = remote_session_manager.generate_pairing_code()
    session = remote_session_manager.exchange_pairing_code(code, "127.0.0.1")

    # Mock agent reply to test end-to-end
    from app.services.agent_service import AgentResponse
    async def mock_chat(msg, **kwargs):
        return AgentResponse(success=True, message=f"Echo: {msg}", tools_executed=[])
    monkeypatch.setattr("app.services.agent_service.agent_service.chat", mock_chat)

    auth_resp = client.post(
        "/api/chat",
        json={"message": "System status"},
        headers={
            "Origin": PROD_ORIGIN,
            "Authorization": f"Bearer {session.token}"
        }
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["reply"] == "Echo: System status"


def test_unauthorized_origins_rejected_by_middleware(client: TestClient):
    """Middleware must reject untrusted origins with 403 Forbidden."""
    untrusted = [
        "https://malicious-site.com",
        "http://evil.org",
        "https://phishing.app",
        "http://192.168.1.50:3000",
    ]
    for origin in untrusted:
        resp = client.get("/health", headers={"Origin": origin})
        assert resp.status_code == 403, f"Expected 403 for origin {origin}"
        assert "not authorized" in resp.json()["detail"]

    # Approved origins must pass
    for approved in [PROD_ORIGIN, PREVIEW_ORIGIN, "http://localhost:8000", "http://127.0.0.1:8000"]:
        resp = client.get("/health", headers={"Origin": approved})
        assert resp.status_code == 200, f"Expected 200 for origin {approved}"


def test_host_header_tailscale_allowed_and_unauthorized_rejected(client: TestClient):
    """DNS rebinding protection: only localhost and Tailscale addresses are permitted."""
    assert is_allowed_host("localhost") is True
    assert is_allowed_host("127.0.0.1:8000") is True
    assert is_allowed_host("testserver") is True
    assert is_allowed_host("my-laptop.tailnet-xyz.ts.net") is True
    assert is_allowed_host("my-laptop.tailnet-xyz.ts.net:443") is True
    assert is_allowed_host("100.85.12.34:8000") is True

    # Unauthorized external hosts rejected
    assert is_allowed_host("attacker.com") is False
    assert is_allowed_host("bad-domain.org:8000") is False

    # Check middleware enforcement
    bad_host_resp = client.get("/health", headers={"Host": "attacker.com"})
    assert bad_host_resp.status_code == 403
    assert "Host 'attacker.com' is not authorized" in bad_host_resp.json()["detail"]


def test_remote_origin_requires_session_token_for_data_endpoints(client: TestClient):
    """Regression test (critical fix): remote requests without a session token
    must be rejected with 401 on data/memory/gmail endpoints, not just /api/chat."""
    remote_headers = {"Origin": PROD_ORIGIN}
    for method, url in [
        ("GET", "/api/memories"),
        ("GET", "/api/data/export"),
        ("GET", "/api/gmail/messages"),
        ("GET", "/api/reminders"),
        ("GET", "/api/calendar/events"),
        ("POST", "/api/data/clear"),
        ("POST", "/api/browser/approve-domain"),
        ("GET", "/api/briefing"),
    ]:
        kwargs = {"headers": remote_headers}
        if method == "POST" and "clear" in url:
            kwargs["json"] = {"confirm": True, "confirmation_text": "DELETE ALL DATA"}
        elif method == "POST":
            kwargs["json"] = {"domain": "example.com"}
        resp = client.request(method, url, **kwargs)
        assert resp.status_code == 401, f"{method} {url} returned {resp.status_code}, expected 401"
        assert "Sign-in required" in resp.json()["detail"]

    # With a valid session token the same endpoints succeed (memories: 200, empty list)
    code = remote_session_manager.generate_pairing_code()
    session = remote_session_manager.exchange_pairing_code(code, "127.0.0.1")
    auth_headers = {"Origin": PROD_ORIGIN, "Authorization": f"Bearer {session.token}"}
    ok_resp = client.get("/api/memories", headers=auth_headers)
    assert ok_resp.status_code == 200

    # Public endpoints stay public remotely: /health and /remote/session/status
    assert client.get("/health", headers=remote_headers).status_code == 200
    assert client.get("/api/remote/session/status", headers=remote_headers).status_code == 200


def test_remote_stop_endpoint(client: TestClient):
    """Remote stop honestly reports that stopping is not supported."""
    code = remote_session_manager.generate_pairing_code()
    session = remote_session_manager.exchange_pairing_code(code, "127.0.0.1")

    stop_resp = client.post(
        "/api/remote/stop",
        headers={
            "Origin": PROD_ORIGIN,
            "Authorization": f"Bearer {session.token}"
        }
    )
    assert stop_resp.status_code == 200
    assert stop_resp.json()["stopped"] is False
    assert "not supported" in stop_resp.json()["message"]


def test_backend_security_architecture_binding_and_no_relay():
    """Verify backend remains strictly bound to 127.0.0.1 and has no public relay."""
    assert settings.HOST == "127.0.0.1", "Backend MUST bind strictly to 127.0.0.1"
    assert settings.ALLOW_REMOTE_ACCESS is False, "Remote access override must be False by default"
    
    # Confirm configuration raises error if bound to public 0.0.0.0
    from app.core.config import Settings, ConfigurationError
    with pytest.raises(ConfigurationError):
        bad_settings = Settings(HOST="0.0.0.0", ALLOW_REMOTE_ACCESS=False)
        bad_settings.validate_configuration()
