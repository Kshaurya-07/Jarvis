import sys
from unittest.mock import MagicMock, patch
import pytest

from app.core.confirmation import confirmation_manager
from app.tools.app_control_tools import open_application, ALLOWED_APPLICATIONS


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only app-control tool")
def test_open_app_not_in_allowlist():
    result = open_application("powershell")
    assert result.success is False
    assert "not in the server-side allowlist" in result.error


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only app-control tool")
def test_open_app_arbitrary_path_rejected():
    result = open_application("C:\\Windows\\System32\\cmd.exe /c calc")
    assert result.success is False
    assert "not in the server-side allowlist" in result.error


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only app-control tool")
def test_open_app_requires_confirmation():
    result = open_application("calculator")
    assert result.success is False
    assert "Confirmation required" in result.error
    assert result.output["requires_confirmation"] is True
    assert "confirmation_id" in result.output
    assert result.output["app_name"] == "calculator"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only app-control tool")
def test_open_app_with_confirmed_token():
    # 1. Trigger pending action
    res1 = open_application("notepad")
    conf_id = res1.output["confirmation_id"]

    # 2. Confirm the action
    confirmation_manager.confirm_action(conf_id)

    # 3. Execute with confirmation_id (mock subprocess to avoid opening actual window during test)
    mock_proc = MagicMock()
    mock_proc.pid = 12345
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        res2 = open_application("notepad", confirmation_id=conf_id)
        assert res2.success is True
        assert res2.output["pid"] == 12345
        assert "Successfully launched Notepad" in res2.output["message"]
        mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only app-control tool")
def test_open_app_cannot_reuse_confirmation_token():
    res1 = open_application("notepad")
    conf_id = res1.output["confirmation_id"]
    confirmation_manager.confirm_action(conf_id)

    mock_proc = MagicMock()
    mock_proc.pid = 12345
    with patch("subprocess.Popen", return_value=mock_proc):
        # First use succeeds
        res2 = open_application("notepad", confirmation_id=conf_id)
        assert res2.success is True

        # Second use with same token fails (single-use token)
        res3 = open_application("notepad", confirmation_id=conf_id)
        assert res3.success is False
        assert "invalid, expired" in res3.error


def test_open_app_unsupported_platform():
    with patch("sys.platform", "linux"):
        result = open_application("notepad")
        assert result.success is False
        assert "only supported on Windows" in result.error
