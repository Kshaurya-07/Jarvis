import json
import os
from pathlib import Path
import pytest

from app.core.config import Settings, ConfigurationError, settings
from app.core.logger import action_logger, scrub_sensitive_text
from app.core.rate_limiter import auth_rate_limiter
from app.core.security import resolve_safe_path, SecurityViolationError
from app.core.data_manager import user_data_manager
from app.tools.notes_tools import create_note
from app.tools.reminders_tools import reminders_storage
from app.tools.memory_tools import memory_storage


# --- 1. Security Review & Network Boundary Tests ---

def test_dns_rebinding_defense(client):
    """Verify that unauthorized Host headers (e.g. from DNS rebinding attacks) are blocked with 403."""
    # Attack payload: attacker domain resolving to 127.0.0.1
    res = client.get("/health", headers={"Host": "attacker-controlled-domain.com"})
    assert res.status_code == 403
    assert "Host" in res.json()["detail"]
    assert "not authorized" in res.json()["detail"]

    # Valid localhost Host header
    res_valid = client.get("/health", headers={"Host": "localhost:8000"})
    assert res_valid.status_code == 200

    res_valid_ip = client.get("/health", headers={"Host": "127.0.0.1:8000"})
    assert res_valid_ip.status_code == 200


def test_cross_site_referer_blocked_for_state_changing_methods(client):
    """Verify that state-changing requests with foreign Referer headers are blocked."""
    # Unauthorized referer on POST without origin
    res = client.post(
        "/api/chat",
        headers={"Referer": "https://malicious-website.com/index.html"},
        json={"message": "hello"},
    )
    assert res.status_code == 403
    assert "Referer" in res.json()["detail"]

    # Localhost referer is permitted
    res_ok = client.get("/health", headers={"Referer": "http://localhost:8000/mobile/"})
    assert res_ok.status_code == 200


def test_request_body_size_limit_middleware(client, monkeypatch):
    """Verify that incoming requests exceeding MAX_REQUEST_BODY_BYTES are rejected with 413."""
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 500)
    # Header claims 600 bytes
    res = client.post(
        "/api/chat",
        headers={"Content-Length": "600"},
        content=b"A" * 600,
    )
    assert res.status_code == 413
    assert "Request entity too large" in res.json()["detail"]


def test_auth_failure_rate_limiting(client):
    """Verify that consecutive authentication or confirmation failures trigger HTTP 429 Too Many Requests."""
    auth_rate_limiter.reset()

    # Repeatedly attempt confirmation with invalid confirmation_id
    for _ in range(settings.AUTH_FAILURE_RATE_LIMIT):
        res = client.post("/api/confirm", json={"confirmation_id": "nonexistent_token", "approve": True})
        assert res.status_code == 404

    # The next attempt must be blocked by rate limiting (429)
    res_limited = client.post("/api/confirm", json={"confirmation_id": "nonexistent_token", "approve": True})
    assert res_limited.status_code == 429
    assert "Too many authentication or confirmation failures" in res_limited.json()["detail"]
    assert "Retry-After" in res_limited.headers

    # Reset cleans up state
    auth_rate_limiter.reset()
    res_after_reset = client.post("/api/confirm", json={"confirmation_id": "nonexistent_token", "approve": True})
    assert res_after_reset.status_code == 404


def test_oauth_callback_failure_rate_limiting(client):
    """Verify that repeated invalid OAuth callbacks trigger rate limiting."""
    auth_rate_limiter.reset()

    for _ in range(settings.AUTH_FAILURE_RATE_LIMIT):
        res = client.get("/api/auth/google/callback?code=bad_code&state=bad_state")
        assert res.status_code in (400, 500)

    res_blocked = client.get("/api/auth/google/callback?code=bad_code&state=bad_state")
    assert res_blocked.status_code == 429
    auth_rate_limiter.reset()


# --- 2. Filesystem & Path Security Tests ---

def test_alternate_data_stream_rejection(tmp_path: Path):
    """Verify that NTFS alternate data streams (using colons) are strictly rejected."""
    with pytest.raises(SecurityViolationError):
        resolve_safe_path(tmp_path, "notes.txt:hidden_stream", must_exist=False)

    with pytest.raises(SecurityViolationError):
        resolve_safe_path(tmp_path, "sub/file.py::$DATA", must_exist=False)


def test_symlink_escape_rejection(tmp_path: Path):
    """Verify that a symlink pointing outside the base directory raises SecurityViolationError."""
    inside_dir = tmp_path / "inside"
    outside_dir = tmp_path / "outside"
    inside_dir.mkdir()
    outside_dir.mkdir()

    secret_file = outside_dir / "secret.txt"
    secret_file.write_text("secret_data", encoding="utf-8")

    link = inside_dir / "evil_link.txt"
    try:
        os.symlink(secret_file, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported or requires elevated privileges in this environment.")

    # Accessing the link must be blocked because it resolves outside inside_dir
    with pytest.raises(SecurityViolationError):
        resolve_safe_path(inside_dir, "evil_link.txt", must_exist=True)


# --- 3. Audit Log Redaction Tests ---

def test_scrub_sensitive_text():
    """Verify that regex scrubbing redacts secrets, API keys, tokens, emails, and card numbers."""
    raw = (
        "Error occurred with api_key: AIzaSyD3x9183fakekey12345678901234 "
        "and bearer secret_bearer_token_xyz_123456789. "
        "User email was test.user@example.com, card was 4111 2222 3333 4444."
    )
    scrubbed = scrub_sensitive_text(raw)
    assert "[REDACTED_SECRET]" in scrubbed or "[REDACTED_KEY]" in scrubbed
    assert "[REDACTED_TOKEN]" in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_CARD]" in scrubbed
    assert "test.user@example.com" not in scrubbed
    assert "4111 2222 3333 4444" not in scrubbed
    assert "AIzaSyD3x9183fakekey12345678901234" not in scrubbed


def test_action_logger_never_persists_secrets_to_disk(tmp_path: Path):
    """Verify ActionLogger strips keys and passwords before saving to disk."""
    log_file = tmp_path / "actions.jsonl"
    logger = action_logger.__class__(log_file=log_file)

    logger.record_action(
        tool_name="test_tool",
        status="failure",
        details="Authentication error with password=SuperSecretPassword123 and api_key: AIzaFakeKey1234567890123456789012345",
    )

    content = log_file.read_text(encoding="utf-8")
    assert "SuperSecretPassword123" not in content
    assert "AIzaFakeKey1234567890123456789012345" not in content
    assert "[REDACTED_SECRET]" in content or "[REDACTED_KEY]" in content


# --- 4. Configuration Validation Tests ---

def test_startup_configuration_validation():
    """Verify configuration validation catches unsafe host bindings and bad settings."""
    # 1. Non-localhost host rejected by default
    unsafe_settings = Settings(HOST="0.0.0.0", ALLOW_REMOTE_ACCESS=False)
    with pytest.raises(ConfigurationError) as exc:
        unsafe_settings.validate_configuration()
    assert "Security Violation" in str(exc.value)

    # 2. Non-localhost permitted with explicit ALLOW_REMOTE_ACCESS=True
    override_settings = Settings(HOST="0.0.0.0", ALLOW_REMOTE_ACCESS=True)
    warnings = override_settings.validate_configuration()
    assert isinstance(warnings, list)

    # 3. Invalid port
    bad_port_settings = Settings(PORT=99999)
    with pytest.raises(ConfigurationError):
        bad_port_settings.validate_configuration()

    # 4. Invalid search provider
    bad_search_settings = Settings(SEARCH_PROVIDER="unsupported_provider")
    with pytest.raises(ConfigurationError):
        bad_search_settings.validate_configuration()

    # 5. Missing GEMINI_API_KEY generates informational notice
    default_settings = Settings(GEMINI_API_KEY="")
    notices = default_settings.validate_configuration()
    assert any("GEMINI_API_KEY" in n for n in notices)


# --- 5. User Data Controls & Data Management Tests ---

def test_data_locations_endpoint(client):
    """Verify GET /api/data/locations returns all local directories and storage status."""
    res = client.get("/api/data/locations")
    assert res.status_code == 200
    data = res.json()
    assert "locations" in data
    assert "workspace_directory" in data["locations"]
    assert "notes_directory" in data["locations"]
    assert "reminders_file" in data["locations"]
    assert "memories_file" in data["locations"]
    assert "oauth_storage" in data
    assert "disclosure" in data


def test_data_export_endpoint(client):
    """Verify GET /api/data/export returns user-owned notes, reminders, and memories without secrets."""
    # Create sample data
    create_note("Project Plan", "# Q4 Objectives and Deliverables")
    reminders_storage.add("Review security architecture", "2026-12-01T10:00:00Z")
    memory_storage.put("favorite_editor", "VS Code")

    res = client.get("/api/data/export")
    assert res.status_code == 200
    export = res.json()

    assert export["export_format_version"] == "1.0"
    assert export["summary"]["notes_count"] >= 1
    assert export["summary"]["reminders_count"] >= 1
    assert export["summary"]["memories_count"] >= 1

    # Check note content
    notes = export["data"]["notes"]
    assert any("Q4 Objectives" in n["content"] for n in notes)

    # Privacy guarantee: confirm no secrets
    raw_str = json.dumps(export)
    assert "GEMINI_API_KEY" not in raw_str
    assert "GOOGLE_CLIENT_SECRET" not in raw_str


def test_data_clear_requires_confirmation(client):
    """Verify POST /api/data/clear requires exact confirmation_text='DELETE ALL DATA'."""
    # Missing/invalid confirmation rejected
    res1 = client.post("/api/data/clear", json={"confirm": False, "confirmation_text": "no"})
    assert res1.status_code == 400
    assert "Confirmation required" in res1.json()["detail"]

    res2 = client.post("/api/data/clear", json={"confirm": True, "confirmation_text": "please delete"})
    assert res2.status_code == 400

    # Create dummy note & memory
    create_note("Temp Note", "Will be deleted")
    memory_storage.put("temp_key", "Will be deleted")

    # Authorize deletion
    res_ok = client.post("/api/data/clear", json={"confirm": True, "confirmation_text": "DELETE ALL DATA"})
    assert res_ok.status_code == 200
    result = res_ok.json()
    assert result["status"] == "cleared"
    assert result["deleted_items"]["notes"] >= 1
    assert result["deleted_items"]["memories"] >= 1

    # Confirm files wiped
    assert len(memory_storage.list_all()) == 0


def test_google_disconnect_revocation_instructions(client):
    """Verify POST /api/auth/google/disconnect returns clear manual revocation instructions."""
    res = client.post("/api/auth/google/disconnect")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "disconnected"
    assert "https://myaccount.google.com/permissions" in data["revocation_guide"]


# --- 6. Backup & Recovery Tests ---

def test_backup_and_restore_lifecycle(client):
    """Verify end-to-end local backup creation, integrity validation, and restore lifecycle."""
    # 1. Populate initial data
    create_note("Architecture Guide", "# System Architecture Overview")
    reminders_storage.add("Team standup sync", "2026-11-15T09:00:00Z")
    memory_storage.put("user_nickname", "Skywalker")

    # 2. Create backup
    res_backup = client.post("/api/data/backup", json={"backup_name": "release_snap"})
    assert res_backup.status_code == 200
    backup_data = res_backup.json()
    assert backup_data["status"] == "created"
    filename = backup_data["backup_filename"]
    assert "release_snap" in filename
    assert len(backup_data["checksum"]) == 64

    # 3. List backups
    res_list = client.get("/api/data/backups")
    assert res_list.status_code == 200
    backups = res_list.json()["backups"]
    assert any(b["filename"] == filename and b["is_valid"] is True for b in backups)

    # 4. Modify data (simulate loss/corruption)
    memory_storage.clear()
    create_note("Unrelated Note", "New content")

    # 5. Restore without confirm_overwrite fails because existing data is present
    res_restore_denied = client.post(
        "/api/data/restore",
        json={"backup_filename": filename, "confirm_overwrite": False},
    )
    assert res_restore_denied.status_code == 400
    assert "Existing local data found" in res_restore_denied.json()["detail"]

    # 6. Restore with confirm_overwrite=True succeeds
    res_restore = client.post(
        "/api/data/restore",
        json={"backup_filename": filename, "confirm_overwrite": True},
    )
    assert res_restore.status_code == 200
    restore_info = res_restore.json()
    assert restore_info["status"] == "restored"
    assert restore_info["restored_items"]["memories"] >= 1

    # 7. Verify restored content matches original
    assert memory_storage.get("user_nickname") is not None
    assert memory_storage.get("user_nickname").content == "Skywalker"


def test_backup_validation_tamper_rejection():
    """Verify that tampered backup files fail checksum verification."""
    # Create valid backup
    backup_info = user_data_manager.create_backup("tamper_test")
    backup_path = Path(backup_info["backup_path"])

    # Read and tamper with content
    content = json.loads(backup_path.read_text(encoding="utf-8"))
    content["data"]["notes"].append({"filename": "hacked.md", "title": "hacked", "content": "injected"})
    backup_path.write_text(json.dumps(content), encoding="utf-8")

    # Validation must raise ValueError due to checksum mismatch
    with pytest.raises(ValueError) as exc:
        user_data_manager.restore_backup(backup_info["backup_filename"], confirm_overwrite=True)
    assert "checksum mismatch" in str(exc.value).lower()


def test_backup_validation_path_traversal_rejection():
    """Verify that backup files containing malicious traversal note filenames are rejected."""
    bad_backup = {
        "jarvis_backup_version": "1.0",
        "created_at": "2026-11-09T00:00:00Z",
        "data": {
            "notes": [{"filename": "../../etc/malicious.md", "content": "evil content"}],
            "reminders": [],
            "memories": [],
        },
    }
    # Calculate checksum for the bad data
    bad_backup["checksum"] = user_data_manager._compute_checksum(bad_backup["data"])

    with pytest.raises(ValueError) as exc:
        user_data_manager.validate_backup_content(bad_backup)
    assert "path traversal" in str(exc.value).lower()
