from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from app.core.config import settings
from app.core.confirmation import confirmation_manager
from app.tools.screenshot_tools import capture_screenshot, analyze_screenshot


def test_capture_screenshot_requires_confirmation():
    result = capture_screenshot()
    assert result.success is False
    assert "Confirmation required" in result.error
    assert result.output["requires_confirmation"] is True
    assert "confirmation_id" in result.output


def test_capture_screenshot_success(tmp_path: Path, monkeypatch):
    test_screenshots_dir = tmp_path / "screenshots"
    test_screenshots_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "SCREENSHOTS_DIR", test_screenshots_dir)

    # 1. Initiate action
    res1 = capture_screenshot()
    conf_id = res1.output["confirmation_id"]

    # 2. Confirm action
    confirmation_manager.confirm_action(conf_id)

    # 3. Create dummy image for capture
    dummy_img = Image.new("RGB", (100, 100), color="blue")
    with patch("app.tools.screenshot_tools._grab_primary_display", return_value=dummy_img):
        res2 = capture_screenshot(confirmation_id=conf_id)
        assert res2.success is True
        assert res2.output["local_only"] is True
        assert res2.output["dimensions"] == "100x100"
        saved_file = Path(res2.output["saved_path"])
        assert saved_file.exists()
        assert saved_file.parent == test_screenshots_dir


def test_capture_screenshot_display_unavailable():
    res1 = capture_screenshot()
    conf_id = res1.output["confirmation_id"]
    confirmation_manager.confirm_action(conf_id)

    with patch("app.tools.screenshot_tools._grab_primary_display", side_effect=RuntimeError("Display session locked")):
        res2 = capture_screenshot(confirmation_id=conf_id)
        assert res2.success is False
        assert "Display session locked" in res2.error


def test_analyze_screenshot_requires_confirmation(tmp_path: Path, monkeypatch):
    test_screenshots_dir = tmp_path / "screenshots"
    test_screenshots_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "SCREENSHOTS_DIR", test_screenshots_dir)

    dummy_file = test_screenshots_dir / "sample.png"
    dummy_file.write_bytes(b"dummy image bytes")

    result = analyze_screenshot(screenshot_filename="sample.png")
    assert result.success is False
    assert "Confirmation required" in result.error
    assert "Transmitting local screenshot" in result.error
    assert result.output["requires_confirmation"] is True
    assert "confirmation_id" in result.output


def test_analyze_screenshot_with_confirmation(tmp_path: Path, monkeypatch):
    test_screenshots_dir = tmp_path / "screenshots"
    test_screenshots_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "SCREENSHOTS_DIR", test_screenshots_dir)

    dummy_file = test_screenshots_dir / "sample.png"
    dummy_file.write_bytes(b"dummy image bytes")

    # 1. Trigger pending
    res1 = analyze_screenshot(screenshot_filename="sample.png", prompt="What is this?")
    conf_id = res1.output["confirmation_id"]

    # 2. Confirm
    confirmation_manager.confirm_action(conf_id)

    # 3. Execute with mock Gemini client
    mock_gemini_response = MagicMock()
    mock_gemini_response.text = "This is a blue desktop window."

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_gemini_response

    with patch("app.services.agent_service.agent_service._get_client", return_value=mock_client):
        res2 = analyze_screenshot(
            screenshot_filename="sample.png",
            prompt="What is this?",
            confirmation_id=conf_id,
        )
        assert res2.success is True
        assert res2.output["analysis"] == "This is a blue desktop window."
        assert res2.output["external_api_used"] == "Gemini Multimodal"
