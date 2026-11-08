import shutil
import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.rate_limiter import auth_rate_limiter
from app.main import app
from app.tools.reminders_tools import reminders_storage
from app.tools.memory_tools import memory_storage


@pytest.fixture(autouse=True)
def setup_isolated_env(tmp_path: Path, monkeypatch):
    """Isolate workspace, notes, reminders, memory, and log directories for each test."""
    test_workspace = tmp_path / "workspace"
    test_notes = tmp_path / "notes"
    test_screenshots = tmp_path / "screenshots"
    test_data = tmp_path / "data"
    test_backups = tmp_path / "backups"
    test_reminders = test_data / "reminders.json"
    test_memories = test_data / "memories.json"
    test_logs = tmp_path / "logs" / "actions.jsonl"

    test_workspace.mkdir(parents=True, exist_ok=True)
    test_notes.mkdir(parents=True, exist_ok=True)
    test_screenshots.mkdir(parents=True, exist_ok=True)
    test_data.mkdir(parents=True, exist_ok=True)
    test_backups.mkdir(parents=True, exist_ok=True)
    test_logs.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "WORKSPACE_DIR", test_workspace)
    monkeypatch.setattr(settings, "NOTES_DIR", test_notes)
    monkeypatch.setattr(settings, "SCREENSHOTS_DIR", test_screenshots)
    monkeypatch.setattr(settings, "DATA_DIR", test_data)
    monkeypatch.setattr(settings, "BACKUPS_DIR", test_backups)
    monkeypatch.setattr(settings, "REMINDERS_FILE", test_reminders)
    monkeypatch.setattr(settings, "MEMORIES_FILE", test_memories)
    monkeypatch.setattr(settings, "ACTION_LOG_FILE", test_logs)
    monkeypatch.setattr(settings, "MAX_FILE_READ_BYTES", 1024 * 50)  # 50 KB for test
    monkeypatch.setattr(settings, "MAX_REQUEST_LENGTH", 500)
    monkeypatch.setattr(settings, "MEMORY_ENABLED", True)

    monkeypatch.setattr(reminders_storage, "file_path", test_reminders)
    monkeypatch.setattr(memory_storage, "file_path", test_memories)
    auth_rate_limiter.reset()

    yield {
        "workspace": test_workspace,
        "notes": test_notes,
        "screenshots": test_screenshots,
        "data": test_data,
        "backups": test_backups,
        "reminders": test_reminders,
        "memories": test_memories,
        "logs": test_logs,
    }


@pytest.fixture
def client():
    """FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client
