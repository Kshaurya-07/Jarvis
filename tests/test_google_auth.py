import json
import sys
import time
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import settings
from app.core.google_auth import (
    google_auth_manager,
    GoogleAuthManager,
    GoogleConfigError,
    GoogleAuthError,
    GoogleTokenRevokedError,
    KEYRING_SERVICE_NAME,
    KEYRING_USERNAME,
)


def test_pkce_generation():
    """Verify PKCE code_verifier and S256 code_challenge generation."""
    verifier, challenge = GoogleAuthManager.generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(verifier) <= 128
    assert len(challenge) > 20
    # Different calls produce different tokens
    v2, c2 = GoogleAuthManager.generate_pkce_pair()
    assert verifier != v2
    assert challenge != c2


def test_google_auth_url_missing_client_id(monkeypatch):
    """Verify clear actionable error when GOOGLE_CLIENT_ID is not configured."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    with pytest.raises(GoogleConfigError) as exc_info:
        google_auth_manager.create_authorization_url()
    assert "Google Client ID is not configured" in str(exc_info.value)
    assert "README.md" in str(exc_info.value)


def test_google_auth_url_generation_success(monkeypatch):
    """Verify authorization URL includes PKCE, anti-CSRF state, and read-only scopes."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")

    url, state = google_auth_manager.create_authorization_url()
    assert "accounts.google.com/o/oauth2/v2/auth" in url
    assert "client_id=test-client-id.apps.googleusercontent.com" in url
    assert "code_challenge_method=S256" in url
    assert "code_challenge=" in url
    assert f"state={state}" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    # Scopes must be strictly read-only
    assert "gmail.readonly" in url
    assert "calendar.readonly" in url
    # No write scopes!
    assert "gmail.send" not in url
    assert "gmail.compose" not in url
    assert "gmail.modify" not in url
    assert "calendar.events" not in url or "calendar.readonly" in url


def test_state_validation_and_expiration(monkeypatch):
    """Verify OAuth state validation, single-use consumption, and expiration rejection."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-id")
    url, state = google_auth_manager.create_authorization_url()

    # Consuming with wrong state fails
    with pytest.raises(GoogleAuthError) as err:
        google_auth_manager.validate_and_consume_state("invalid_state_token")
    assert "Invalid or expired OAuth state parameter" in str(err.value)

    # Consuming with valid state succeeds
    pending = google_auth_manager.validate_and_consume_state(state)
    assert pending.state == state
    assert len(pending.code_verifier) > 40

    # Cannot consume same state twice (prevent CSRF replay attacks)
    with pytest.raises(GoogleAuthError):
        google_auth_manager.validate_and_consume_state(state)


def test_expired_state_rejected(monkeypatch):
    """Verify expired state (>10 minutes) is rejected."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-id")
    url, state = google_auth_manager.create_authorization_url()

    # Artificially age the state
    google_auth_manager._pending_states[state].created_at = time.time() - 700

    with pytest.raises(GoogleAuthError) as err:
        google_auth_manager.validate_and_consume_state(state)
    assert "expired" in str(err.value).lower()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a usable OS credential store (keyring), unavailable on Linux CI")
def test_token_exchange_mocked(monkeypatch):
    """Verify OAuth code exchange uses PKCE verifier and stores tokens."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")

    url, state = google_auth_manager.create_authorization_url()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "access_token": "mock_access_token_123",
        "refresh_token": "mock_refresh_token_456",
        "expires_in": 3600,
        "token_type": "Bearer",
        # Mock unverified JWT with email in payload
        # Header: {"alg":"none"}, Payload: {"email":"user@example.com"}
        "id_token": "eyJhbGciOiJub25lIn0.eyJlbWFpbCI6InVzZXJAZXhhbXBsZS5jb20ifQ.",
    }

    stored_in_keyring = {}

    def mock_set_password(service, username, value):
        stored_in_keyring[(service, username)] = value

    def mock_get_password(service, username):
        return stored_in_keyring.get((service, username))

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        with patch("keyring.set_password", side_effect=mock_set_password):
            with patch("keyring.get_password", side_effect=mock_get_password):
                res = google_auth_manager.exchange_code(code="mock_auth_code", state=state)
                assert res["status"] == "connected"
                assert res["account_email"] == "user@example.com"
                assert (KEYRING_SERVICE_NAME, KEYRING_USERNAME) in stored_in_keyring

                saved_data = json.loads(stored_in_keyring[(KEYRING_SERVICE_NAME, KEYRING_USERNAME)])
                assert saved_data["refresh_token"] == "mock_refresh_token_456"
                assert saved_data["account_email"] == "user@example.com"

                # Check post data sent to Google
                sent_data = mock_post.call_args[1]["data"]
                assert sent_data["code"] == "mock_auth_code"
                assert sent_data["grant_type"] == "authorization_code"
                assert "code_verifier" in sent_data


def test_storage_fallback_requires_opt_in(monkeypatch, tmp_path):
    """Verify that when OS keyring is unavailable, fallback requires explicit opt-in."""
    monkeypatch.setattr(settings, "GOOGLE_CREDENTIAL_FALLBACK_OPT_IN", False)

    mock_kr = MagicMock()
    mock_kr.priority = 0  # Unavailable or dummy keyring

    with patch("keyring.get_keyring", return_value=mock_kr):
        with patch("keyring.set_password", side_effect=RuntimeError("No secret service")):
            with pytest.raises(RuntimeError) as exc_info:
                google_auth_manager._save_raw_payload({"access_token": "xyz"})
            assert "Operating system credential store is unavailable" in str(exc_info.value)
            assert "GOOGLE_CREDENTIAL_FALLBACK_OPT_IN=true" in str(exc_info.value)


def test_storage_fallback_when_opted_in(monkeypatch, tmp_path):
    """Verify that fallback storage works when GOOGLE_CREDENTIAL_FALLBACK_OPT_IN is True."""
    fallback_file = tmp_path / "data" / "protected_google_token.json"
    monkeypatch.setattr(settings, "GOOGLE_CREDENTIAL_FALLBACK_OPT_IN", True)
    monkeypatch.setattr(settings, "GOOGLE_FALLBACK_TOKEN_FILE", fallback_file)

    mock_kr = MagicMock()
    mock_kr.priority = 0

    with patch("keyring.get_keyring", return_value=mock_kr):
        with patch("keyring.set_password", side_effect=RuntimeError("Keyring fail")):
            with patch("keyring.get_password", return_value=None):
                payload = {"access_token": "abc", "refresh_token": "ref123", "account_email": "optin@example.com"}
                google_auth_manager._save_raw_payload(payload)

                assert fallback_file.exists()
                loaded = google_auth_manager._load_raw_payload()
                assert loaded["refresh_token"] == "ref123"
                assert loaded["account_email"] == "optin@example.com"


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a usable OS credential store (keyring), unavailable on Linux CI")
def test_disconnect_and_revoke():
    """Verify disconnect revokes token with Google and cleans local credentials."""
    stored = {
        (KEYRING_SERVICE_NAME, KEYRING_USERNAME): json.dumps({
            "access_token": "acc_tok",
            "refresh_token": "ref_tok",
            "account_email": "test@example.com",
        })
    }

    def mock_get(s, u):
        return stored.get((s, u))

    def mock_del(s, u):
        stored.pop((s, u), None)

    mock_revoke_resp = MagicMock()
    mock_revoke_resp.status_code = 200

    with patch("keyring.get_password", side_effect=mock_get):
        with patch("keyring.delete_password", side_effect=mock_del):
            with patch("httpx.Client.post", return_value=mock_revoke_resp) as mock_post:
                res = google_auth_manager.disconnect()
                assert res["status"] == "disconnected"
                assert res["revoked_remotely"] is True
                assert (KEYRING_SERVICE_NAME, KEYRING_USERNAME) not in stored

                # Verify revoke URL was called
                mock_post.assert_called_once()
                assert "https://oauth2.googleapis.com/revoke" in mock_post.call_args[0][0]


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a usable OS credential store (keyring), unavailable on Linux CI")
def test_auth_status_disconnected_and_connected():
    """Verify status reports connection state, scopes, and storage backend."""
    # Disconnected state
    with patch("keyring.get_password", return_value=None):
        st = google_auth_manager.get_status()
        assert st["connected"] is False
        assert st["account_email"] is None
        assert st["read_only"] is True

    # Connected state
    token_json = json.dumps({
        "access_token": "a",
        "refresh_token": "r",
        "account_email": "active@example.com",
        "connected_at": "2026-11-09T00:00:00Z",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    })
    with patch("keyring.get_password", return_value=token_json):
        st = google_auth_manager.get_status()
        assert st["connected"] is True
        assert st["account_email"] == "active@example.com"
        assert st["read_only"] is True


def test_google_auth_api_routes(client, monkeypatch):
    """Verify /api/auth/google/url, /api/auth/google/status, and /api/auth/google/disconnect via HTTP."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")

    # 1. URL endpoint
    res = client.get("/api/auth/google/url")
    assert res.status_code == 200
    data = res.json()
    assert "auth_url" in data
    assert "state" in data
    assert len(data["scopes"]) == 2

    # 2. Status endpoint
    with patch("keyring.get_password", return_value=None):
        res_status = client.get("/api/auth/google/status")
        assert res_status.status_code == 200
        assert res_status.json()["connected"] is False

    # 3. Disconnect endpoint
    with patch("keyring.delete_password", return_value=None):
        res_disc = client.post("/api/auth/google/disconnect")
        assert res_disc.status_code == 200
        assert res_disc.json()["status"] == "disconnected"
