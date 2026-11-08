import shutil
import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def setup_isolated_env(tmp_path: Path, monkeypatch):
    """Isolate workspace, notes, and log directories for each test."""
    test_workspace = tmp_path / "workspace"
    test_notes = tmp_path / "notes"
    test_logs = tmp_path / "logs" / "actions.jsonl"

    test_workspace.mkdir(parents=True, exist_ok=True)
    test_notes.mkdir(parents=True, exist_ok=True)
    test_logs.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "WORKSPACE_DIR", test_workspace)
    monkeypatch.setattr(settings, "NOTES_DIR", test_notes)
    monkeypatch.setattr(settings, "ACTION_LOG_FILE", test_logs)
    monkeypatch.setattr(settings, "MAX_FILE_READ_BYTES", 1024 * 50)  # 50 KB for test
    monkeypatch.setattr(settings, "MAX_REQUEST_LENGTH", 500)

    yield {
        "workspace": test_workspace,
        "notes": test_notes,
        "logs": test_logs,
    }


@pytest.fixture
def client():
    """FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client
