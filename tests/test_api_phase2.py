import sys
from unittest.mock import MagicMock, patch
import pytest

from app.core.confirmation import confirmation_manager


def test_health_check_phase2(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "platform" in data
    assert "screenshots_directory" in data
    assert "open_application" in data["active_tools"]
    assert "get_battery_status" in data["active_tools"]
    assert "get_storage_status" in data["active_tools"]
    assert "get_memory_status" in data["active_tools"]
    assert "capture_screenshot" in data["active_tools"]


def test_list_tools_phase2(client):
    response = client.get("/api/tools")
    assert response.status_code == 200
    tool_names = [t["name"] for t in response.json()]
    assert "open_application" in tool_names
    assert "get_battery_status" in tool_names
    assert "get_storage_status" in tool_names
    assert "get_memory_status" in tool_names
    assert "capture_screenshot" in tool_names
    assert "analyze_screenshot" in tool_names


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only app-control tool (open_application)")
def test_confirm_flow_via_api(client):
    # 1. Create a pending action
    action = confirmation_manager.create_pending_action(
        tool_name="open_application",
        arguments={"app_name": "notepad"},
        description="Launch notepad",
    )
    conf_id = action.confirmation_id

    # 2. Check pending list
    res_pending = client.get("/api/confirm/pending")
    assert res_pending.status_code == 200
    ids = [p["confirmation_id"] for p in res_pending.json()]
    assert conf_id in ids

    # 3. Approve via /api/confirm
    mock_proc = MagicMock()
    mock_proc.pid = 9999
    with patch("subprocess.Popen", return_value=mock_proc):
        res_confirm = client.post("/api/confirm", json={"confirmation_id": conf_id, "approve": True})
        assert res_confirm.status_code == 200
        data = res_confirm.json()
        assert data["success"] is True
        assert data["tool_result"]["output"]["pid"] == 9999


def test_deny_flow_via_api(client):
    action = confirmation_manager.create_pending_action(
        tool_name="capture_screenshot",
        arguments={},
        description="Take screenshot",
    )
    conf_id = action.confirmation_id

    res_deny = client.post("/api/confirm", json={"confirmation_id": conf_id, "approve": False})
    assert res_deny.status_code == 200
    assert "denied and cancelled" in res_deny.json()["message"]


def test_confirm_nonexistent_returns_404(client):
    response = client.post("/api/confirm", json={"confirmation_id": "conf_nonexistent", "approve": True})
    assert response.status_code == 404
