"""Phase 12 tests: Google sign-in, BYOK keys, per-user isolation, Vercel shape.

Cloud-mode tests build their own TestClient after flipping
``settings.CLOUD_MODE`` on (the shared ``client`` fixture runs in local
mode, where loopback requests are the trusted local owner).
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.session import create_oauth_state_token, create_session_token
from app.core.store import get_user_store, reset_user_store
from app.core.user_context import UserIdentity, user_paths
from app.main import app

USER_A = UserIdentity(sub="google-sub-user-a", email="a@example.com", name="User A")
USER_B = UserIdentity(sub="google-sub-user-b", email="b@example.com", name="User B")
TEST_KEY_A = "AIzaSyTestKeyForUserA1234567890abcdefg"
TEST_KEY_B = "AIzaSyTestKeyForUserB1234567890abcdefg"
# Fake new-format AI Studio "auth key" (AQ. + 50 base64url chars). Synthetic —
# never a real key. All keys created in AI Studio since 2026-05-28 use this
# shape instead of the classic AIza… prefix (live bug, 2026-11-11).
TEST_KEY_AQ = "AQ.Qw3rTy6uIo9pAs2dFg4hJk7lZx1cVbNm8Qw3rTy6uIo9pAs2dF"


def auth_headers(user: UserIdentity) -> dict:
    return {"Authorization": f"Bearer {create_session_token(user)}"}


def cloud_client(monkeypatch) -> TestClient:
    """A TestClient with CLOUD_MODE on (fresh lifespan, warnings only)."""
    monkeypatch.setattr(settings, "CLOUD_MODE", True)
    return TestClient(app)


def test_unauth_chat_401_in_cloud_mode(monkeypatch):
    with cloud_client(monkeypatch) as client:
        resp = client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 401
        assert "Sign-in required" in resp.json()["detail"]


def test_unauth_data_endpoints_401_in_cloud_mode(monkeypatch):
    with cloud_client(monkeypatch) as client:
        for method, url in [
            ("get", "/api/reminders"),
            ("get", "/api/memories"),
            ("get", "/api/tools"),
            ("get", "/api/actions"),
            ("get", "/api/briefing"),
            ("get", "/api/chat/history"),
            ("get", "/api/auth/key/status"),
        ]:
            resp = getattr(client, method)(url)
            assert resp.status_code == 401, (method, url, resp.status_code)


def test_health_public_in_cloud_mode_and_leaks_nothing(monkeypatch):
    with cloud_client(monkeypatch) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reminders_count"] == 0
        assert data["memories_count"] == 0
        assert "workspace" not in resp.text
        assert "/tmp" not in resp.text and "/home" not in resp.text


def test_login_url_requires_google_client(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    with TestClient(app) as client:
        resp = client.get("/api/auth/login?format=json")
        assert resp.status_code == 400


def test_login_url_returns_google_url_with_login_scopes(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    with TestClient(app) as client:
        resp = client.get("/api/auth/login?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "openid" in data["auth_url"]
        assert "gmail.readonly" not in data["auth_url"]  # login != Gmail scopes
        assert "jarvis_oauth_state" in resp.cookies


def _assert_well_formed_google_auth_url(url: str, expected: dict):
    """Regression guard for the doubled-params bug (live Google 400, 2026-11-11).

    The old builder did ``f"{k}={httpx.URL('', params={k: v}).query}"`` —
    ``httpx.URL(...).query`` already yields the full ``k=v`` pair, so every
    key was doubled (``client_id=client_id=...``) and Google rejected the
    URL as malformed. Parse the query and require each expected parameter
    exactly once, with the right value, and no key containing '='.
    """
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"
    # No doubled keys anywhere in the raw query string.
    for doubled in (
        "client_id=client_id",
        "redirect_uri=redirect_uri",
        "response_type=response_type",
        "scope=scope",
        "access_type=access_type",
        "prompt=prompt",
        "state=state",
        "code_challenge=code_challenge",
        "code_challenge_method=code_challenge_method",
    ):
        assert doubled not in parsed.query, doubled
    qs = parse_qs(parsed.query)
    assert not any("=" in key for key in qs), qs
    for key, value in expected.items():
        assert qs.get(key) == [value], (key, qs.get(key))
    # No unexpected parameters sneaked in.
    assert set(qs) == set(expected)


def test_login_auth_url_has_no_doubled_params(monkeypatch):
    """Live bug: /api/auth/login returned client_id=client_id=... (Google 400)."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    with TestClient(app) as client:
        resp = client.get("/api/auth/login?format=json")
        assert resp.status_code == 200
        url = resp.json()["auth_url"]
        state = resp.json()["state"]
        from urllib.parse import parse_qs as _pq, urlparse as _up

        parsed_qs = _pq(_up(url).query)
        _assert_well_formed_google_auth_url(
            url,
            {
                "client_id": "test-client-id.apps.googleusercontent.com",
                "redirect_uri": settings.GOOGLE_LOGIN_REDIRECT_URI,
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "online",
                "prompt": "select_account",
                "state": state,
                "code_challenge": parsed_qs["code_challenge"][0],
                "code_challenge_method": "S256",
            },
        )
        assert len(parsed_qs["state"]) == 1 and parsed_qs["state"][0]
        assert len(parsed_qs["code_challenge"]) == 1 and parsed_qs["code_challenge"][0]


def test_gmail_auth_url_has_no_doubled_params(monkeypatch):
    """Same doubled-params bug lived in the Gmail/Calendar URL builder too."""
    from urllib.parse import parse_qs, urlparse

    from app.core.google_auth import google_auth_manager

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    url, state = google_auth_manager.create_authorization_url()
    parsed_qs = parse_qs(urlparse(url).query)
    _assert_well_formed_google_auth_url(
        url,
        {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(settings.GOOGLE_OAUTH_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": parsed_qs["code_challenge"][0],
            "code_challenge_method": "S256",
        },
    )
    assert "gmail.readonly" in parsed_qs["scope"][0]


def test_login_callback_mints_session_and_me_works(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    fake_identity = {"sub": "google-sub-user-a", "email": "a@example.com", "name": "User A"}
    with patch(
        "app.core.google_auth.google_auth_manager.exchange_login_code",
        return_value=fake_identity,
    ):
        with TestClient(app) as client:
            # Start login to get a signed state cookie.
            start = client.get("/api/auth/login?format=json")
            assert start.status_code == 200
            state = start.json()["state"]
            # Callback with the matching state + cookie.
            cb = client.get(
                f"/api/auth/login/callback?format=json&code=fake-code&state={state}"
            )
            assert cb.status_code == 200, cb.text
            token = cb.json()["session_token"]
            assert token.count(".") == 2
            # The minted token authenticates /auth/me.
            me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["authenticated"] is True
            assert me.json()["email"] == "a@example.com"
            assert me.json()["has_key"] is False


def test_login_callback_browser_flow_sets_session_cookie_and_me_authenticates(monkeypatch):
    """Regression: sign-in must stick in the browser. The callback redirects
    (relative URL, same origin so the cookie survives) and sets the session
    cookie; a follow-up /api/auth/me with that cookie must authenticate.
    Before the fix, the redirect went to absolute FRONTEND_URL, so landing on
    the other live domain meant the cookie's origin never matched and the
    Companion kept showing 'You're not signed in yet'."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    fake_identity = {"sub": "google-sub-user-b", "email": "b@example.com", "name": "User B"}
    with patch(
        "app.core.google_auth.google_auth_manager.exchange_login_code",
        return_value=fake_identity,
    ):
        with TestClient(app) as client:
            start = client.get("/api/auth/login?format=json")
            assert start.status_code == 200
            state = start.json()["state"]
            cb = client.get(
                f"/api/auth/login/callback?code=fake-code&state={state}",
                follow_redirects=False,
            )
            assert cb.status_code in (302, 303, 307), cb.text
            # Relative redirect: same origin as the cookie. An absolute
            # FRONTEND_URL redirect would lose the cookie on the other domain.
            assert cb.headers["location"] == "/mobile/?login=success"
            assert "jarvis_session" in cb.headers.get("set-cookie", "")
            # The cookie the callback set authenticates /auth/me.
            me = client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json()["authenticated"] is True
            assert me.json()["email"] == "b@example.com"


def test_login_callback_rejects_state_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    with TestClient(app) as client:
        client.cookies.set("jarvis_oauth_state", create_oauth_state_token("real-state", "verifier-x", "http://127.0.0.1:8000/api/auth/login/callback"))
        resp = client.get("/api/auth/login/callback?format=json&code=x&state=wrong-state")
        assert resp.status_code == 400


def test_auth_me_unauthenticated_in_local_mode(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False


def test_byok_key_save_is_masked_and_encrypted(monkeypatch, tmp_path):
    with cloud_client(monkeypatch) as client:
        # Bad format rejected.
        bad = client.post("/api/auth/key", json={"api_key": "not-a-gemini-key"}, headers=auth_headers(USER_A))
        assert bad.status_code == 400
        # Save a real-looking key.
        resp = client.post("/api/auth/key", json={"api_key": TEST_KEY_A}, headers=auth_headers(USER_A))
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_key"] is True
        assert resp.json()["hint"] == "…defg"
        assert TEST_KEY_A not in resp.text
        # Status never returns the key.
        st = client.get("/api/auth/key/status", headers=auth_headers(USER_A))
        assert st.status_code == 200
        assert st.json()["has_key"] is True
        assert TEST_KEY_A not in st.text
        # At rest it is encrypted bytes, not the plaintext key.
        key_file = user_paths(USER_A).gemini_key_file
        assert key_file.exists()
        assert TEST_KEY_A.encode() not in key_file.read_bytes()
        # Other user has no key.
        st_b = client.get("/api/auth/key/status", headers=auth_headers(USER_B))
        assert st_b.json()["has_key"] is False
        # Delete works.
        deleted = client.delete("/api/auth/key", headers=auth_headers(USER_A))
        assert deleted.json()["deleted"] is True
        assert client.get("/api/auth/key/status", headers=auth_headers(USER_A)).json()["has_key"] is False


def test_aq_auth_key_format_accepted_and_garbage_rejected():
    """Live bug (2026-11-11): new AI Studio keys start with 'AQ.', not 'AIza'.

    validate_key_format() only accepted AIza…, so every key created in AI
    Studio since 2026-05-28 was rejected with "does not look like a Gemini
    API key". Both formats must pass; non-keys must still fail.
    """
    from app.core.byok import ByokError, validate_key_format

    # Both real formats pass (classic + new AQ. auth key).
    validate_key_format(TEST_KEY_A)
    validate_key_format(TEST_KEY_AQ)
    validate_key_format("  " + TEST_KEY_AQ + "\n")  # surrounding whitespace is stripped
    # Non-keys still fail.
    for bad in [
        "not-a-gemini-key",
        "short",
        "AIza",  # prefix only, no key material
        "AIza" + "a" * 10,  # classic shape, too short (total < 30 chars)
        "AQ.",  # prefix only
        "AQ." + "a" * 10,  # AQ. shape, too short (needs 40-60 chars after AQ.)
        "AQ." + "a" * 61,  # AQ. shape, too long
        "AQ." + "a" * 49 + "!",  # illegal character in key material
        "GOCSPX-" + "a" * 28,  # Google OAuth client SECRET, not a Gemini key
        "123456789012-abcdef.apps.googleusercontent.com",  # OAuth client ID
    ]:
        with pytest.raises(ByokError, match="does not look like a Gemini API key"):
            validate_key_format(bad)


def test_aq_auth_key_save_via_endpoint(monkeypatch, tmp_path):
    """A new-format AQ. key saves, is masked, and is encrypted at rest."""
    with cloud_client(monkeypatch) as client:
        resp = client.post("/api/auth/key", json={"api_key": TEST_KEY_AQ}, headers=auth_headers(USER_A))
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_key"] is True
        assert resp.json()["hint"] == "…s2dF"
        assert TEST_KEY_AQ not in resp.text
        st = client.get("/api/auth/key/status", headers=auth_headers(USER_A))
        assert st.json()["has_key"] is True
        assert TEST_KEY_AQ not in st.text
        key_file = user_paths(USER_A).gemini_key_file
        assert key_file.exists()
        assert TEST_KEY_AQ.encode() not in key_file.read_bytes()


def test_aq_auth_key_is_scrubbed_from_logs():
    """Log scrubbing must redact AQ. keys too, not just classic AIza… keys."""
    from app.core.logger import scrub_sensitive_text

    assert TEST_KEY_AQ not in scrub_sensitive_text(f"call failed key={TEST_KEY_AQ}")
    assert "[REDACTED_KEY]" in scrub_sensitive_text(f"call failed key={TEST_KEY_AQ}")
    assert TEST_KEY_A not in scrub_sensitive_text(f"call failed key={TEST_KEY_A}")


def test_chat_without_key_prompts_for_byok_key(monkeypatch):
    with cloud_client(monkeypatch) as client:
        resp = client.post("/api/chat", json={"message": "hello"}, headers=auth_headers(USER_A))
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert resp.json()["error"] == "no_user_gemini_key"
        assert "Gemini key" in resp.json()["reply"]


def test_chat_with_byok_key_records_history(monkeypatch):
    """A chat turn uses the user's own key and lands in their history."""
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured["called"] = True
            return SimpleNamespace(function_calls=None, text="Hello from Gemini!", candidates=None)

    class FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.models = FakeModels()

    with cloud_client(monkeypatch) as client:
        client.post("/api/auth/key", json={"api_key": TEST_KEY_A}, headers=auth_headers(USER_A))
        with patch("app.services.agent_service.AgentService._get_client",
                   side_effect=lambda api_key=None: FakeClient(api_key)):
            resp = client.post("/api/chat", json={"message": "Say hi"}, headers=auth_headers(USER_A))
        assert resp.status_code == 200, resp.text
        assert resp.json()["reply"] == "Hello from Gemini!"
        assert captured["api_key"] == TEST_KEY_A  # the USER's key, not a server key
        hist = client.get("/api/chat/history", headers=auth_headers(USER_A))
        assert hist.status_code == 200
        roles = [m["role"] for m in hist.json()["messages"]]
        assert roles == ["user", "assistant"]
        assert hist.json()["messages"][0]["content"] == "Say hi"
        # Other user sees no history.
        hist_b = client.get("/api/chat/history", headers=auth_headers(USER_B))
        assert hist_b.json()["messages"] == []


def test_per_user_isolation_reminders_memories_notes(monkeypatch):
    with cloud_client(monkeypatch) as client:
        # User A creates a reminder + memory.
        r = client.post("/api/reminders", json={"title": "A secret task", "due_time": "Tomorrow 9am"},
                        headers=auth_headers(USER_A))
        assert r.status_code == 201, r.text
        reminder_id = r.json()["id"]
        m = client.post("/api/memories", json={"key": "fav_food", "content": "A likes biryani"},
                        headers=auth_headers(USER_A))
        assert m.status_code == 201
        from app.tools.notes_tools import create_note, search_notes

        assert create_note("A private note", "A's secret content", user=USER_A).success is True
        assert search_notes("secret", user=USER_A).output["files_matched"] == 1

        # User B sees none of it, and cannot touch A's reminder.
        assert client.get("/api/reminders", headers=auth_headers(USER_B)).json() == []
        assert client.get("/api/memories", headers=auth_headers(USER_B)).json() == []
        assert search_notes("secret", user=USER_B).output["files_matched"] == 0
        assert client.patch(f"/api/reminders/{reminder_id}/complete",
                            headers=auth_headers(USER_B)).status_code == 404
        assert client.delete(f"/api/reminders/{reminder_id}",
                             headers=auth_headers(USER_B)).status_code in (400, 404)
        # User A still sees everything, and export is scoped.
        assert len(client.get("/api/reminders", headers=auth_headers(USER_A)).json()) == 1
        assert len(client.get("/api/memories", headers=auth_headers(USER_A)).json()) == 1
        exp_a = client.get("/api/data/export", headers=auth_headers(USER_A)).json()
        assert exp_a["summary"]["reminders_count"] == 1
        assert exp_a["summary"]["memories_count"] == 1
        assert exp_a["summary"]["notes_count"] == 1
        exp_b = client.get("/api/data/export", headers=auth_headers(USER_B)).json()
        assert exp_b["summary"] == {"notes_count": 0, "reminders_count": 0, "memories_count": 0}
        # Namespaced on disk: A's files live under users/<hash>/, B has no dir data.
        assert user_paths(USER_A).reminders_file.exists()
        assert not user_paths(USER_B).reminders_file.exists()


def test_per_user_usage_caps(monkeypatch):
    from fastapi import HTTPException

    from app.core.usage_limiter import usage_limiter

    monkeypatch.setattr(settings, "GEMINI_CALLS_PER_USER_PER_HOUR", 2)
    monkeypatch.setattr(settings, "GEMINI_CALLS_PER_USER_PER_DAY", 100)
    usage_limiter.check_and_record(USER_A, kind="gemini")
    usage_limiter.check_and_record(USER_A, kind="gemini")
    with pytest.raises(HTTPException) as exc:
        usage_limiter.check_and_record(USER_A, kind="gemini")
    assert exc.value.status_code == 429
    # Caps are per user: B is unaffected.
    usage_limiter.check_and_record(USER_B, kind="gemini")


def test_key_validate_endpoint_reports_no_key(monkeypatch):
    with cloud_client(monkeypatch) as client:
        resp = client.post("/api/auth/key/validate", headers=auth_headers(USER_A))
        assert resp.status_code == 200
        assert resp.json()["has_key"] is False
        assert resp.json()["valid"] is False


def test_gmail_unavailable_in_cloud_mode(monkeypatch):
    with cloud_client(monkeypatch) as client:
        assert client.get("/api/gmail/messages", headers=auth_headers(USER_A)).status_code == 503
        assert client.get("/api/calendar/events", headers=auth_headers(USER_A)).status_code == 503


def test_local_only_tools_refuse_in_cloud_mode(monkeypatch):
    with cloud_client(monkeypatch) as client:
        # System-status tools are local-only; chat with a mocked agent that
        # calls them would surface the refusal — here check the tools directly.
        from app.tools.system_status_tools import get_battery_status, get_memory_status
        from app.tools.app_control_tools import open_application

        assert get_battery_status().success is False
        assert "cloud mode" in get_battery_status().error
        assert get_memory_status().success is False
        assert open_application("notepad").success is False


def test_store_factory_picks_postgres_when_database_url_set(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://user:pass@localhost:5432/jarvis")
    reset_user_store()
    from app.core.store import PostgresUserStore

    assert isinstance(get_user_store(), PostgresUserStore)
    reset_user_store()


def test_vercel_entrypoint_and_config():
    """api/index.py exposes the FastAPI app; vercel.json routes /api/* to it."""
    import importlib.util
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("vercel_index", repo_root / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.app.title.startswith("Jarvis")
    vercel = json.loads((repo_root / "vercel.json").read_text())
    rewrites = vercel["rewrites"]
    # /api/* must route to the function by its extension-less route (/api/index).
    # Destination "/api/index.py" does NOT resolve: live, /api/health 404'd
    # while /api itself invoked the function (500) — the .py destination
    # matches no route. Source uses the documented :path* wildcard.
    assert rewrites[0] == {"source": "/api/:path*", "destination": "/api/index"}
    assert not any(r["destination"].endswith(".py") for r in rewrites)
    assert vercel["functions"]["api/index.py"]["maxDuration"] == 10
    # Other rewrites must exist too: /companion and /companion/ serve the
    # Companion PWA, /landing serves the static landing page. There is no
    # /demo rewrite anymore — the demo section was removed.
    by_source = {r["source"]: r["destination"] for r in rewrites}
    # /companion is an alias for the Companion PWA: destination is the
    # directory ("/mobile/"), not "/mobile/index.html" — with cleanUrls on,
    # a rewrite to an .html file does not resolve live (both /companion and
    # /companion/ 404'd while /mobile/ served 200).
    assert by_source["/companion"] == "/mobile/"
    assert by_source["/companion/"] == "/mobile/"
    assert by_source["/landing"] == "/landing/index.html"
    assert "/demo" not in by_source and "/demo/" not in by_source
    # backend/app/ must be deployed: api/index.py does `from app.main import
    # app`. If .vercelignore excluded it, every invocation would fail with
    # ModuleNotFoundError (live symptom: /api -> 500 FUNCTION_INVOCATION_FAILED).
    vercelignore = (repo_root / ".vercelignore").read_text().splitlines()
    ignored = {ln.strip() for ln in vercelignore if ln.strip() and not ln.strip().startswith("#")}
    assert "backend/app/" not in ignored


class _FakeCursor:
    """Minimal in-memory stand-in for a psycopg cursor (memories + users)."""

    def __init__(self, db):
        self.db = db
        self.description = None
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=()):
        if "CREATE TABLE" in sql or "CREATE INDEX" in sql:
            self._rows, self.rowcount = [], 0
            return
        if sql.startswith("INSERT INTO jarvis_users"):
            self._rows, self.rowcount = [], 0
            return
        if "INSERT INTO jarvis_memories" in sql:
            user_ns, key, content = params
            self.db.setdefault(user_ns, {})[key] = content
            self.description = [SimpleNamespace(name="key"), SimpleNamespace(name="content"),
                                SimpleNamespace(name="created_at"), SimpleNamespace(name="updated_at")]
            import datetime

            now = datetime.datetime.now(datetime.timezone.utc)
            self._rows = [(key, content, now, now)]
            self.rowcount = 1
            return
        if "SELECT memory_key AS key" in sql:
            user_ns = params[0]
            import datetime

            now = datetime.datetime.now(datetime.timezone.utc)
            self._rows = [(k, v, now, now) for k, v in sorted(self.db.get(user_ns, {}).items())]
            self.description = [SimpleNamespace(name="key"), SimpleNamespace(name="content"),
                                SimpleNamespace(name="created_at"), SimpleNamespace(name="updated_at")]
            self.rowcount = len(self._rows)
            return
        raise AssertionError(f"unexpected SQL in fake: {sql[:80]}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return _FakeCursor(self.db)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_postgres_store_scopes_memories_per_user(monkeypatch):
    """The Postgres store SQL is user-scoped: B cannot read A's memories."""
    from app.core.store import PostgresUserStore

    db: dict = {}
    store = PostgresUserStore("postgresql://fake:5432/jarvis")
    with patch("psycopg.connect", return_value=_FakeConn(db)):
        store.put_memory(USER_A, "fav_food", "biryani")
        assert store.list_memories(USER_A)[0]["content"] == "biryani"
        assert store.list_memories(USER_B) == []
        store.put_memory(USER_B, "fav_food", "pizza")
        assert [m["content"] for m in store.list_memories(USER_B)] == ["pizza"]
        assert [m["content"] for m in store.list_memories(USER_A)] == ["biryani"]
