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
    assert rewrites[0] == {"source": "/api/(.*)", "destination": "/api/index.py"}
    assert vercel["functions"]["api/index.py"]["maxDuration"] == 10


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
