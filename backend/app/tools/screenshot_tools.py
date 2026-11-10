import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from PIL import Image

from app.core.config import settings
from app.core.confirmation import confirmation_manager
from app.core.security import verify_windows_os, UnsupportedPlatformError, resolve_safe_path
from app.tools.base import ToolResult


def _grab_primary_display() -> Image.Image:
    """
    Captures primary screen using Pillow ImageGrab or mss.
    Raises RuntimeError if capture is impossible (e.g. locked screen or headless).
    """
    # Attempt 1: Pillow ImageGrab
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        if img:
            return img
    except Exception:
        pass

    # Attempt 2: mss fallback
    try:
        import mss
        with mss.MSS() as sct:
            # Primary monitor is index 1 if multiple, else index 0
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception as e:
        raise RuntimeError(
            f"Screen capture failed. The display may be locked, asleep, or in an inactive session: {str(e)}"
        )


def capture_screenshot(confirmation_id: Optional[str] = None) -> ToolResult:
    """
    Capture the primary display on Windows only when explicitly requested.
    Saves screenshot locally to the configured screenshots directory.
    Requires explicit user confirmation before capturing.
    
    Args:
        confirmation_id: Optional confirmation token if confirmation was already approved.
    """
    try:
        verify_windows_os("capture_screenshot")
    except UnsupportedPlatformError as e:
        return ToolResult(success=False, error=str(e))

    action_args: Dict[str, Any] = {}

    # Confirmation requirement check
    if confirmation_id:
        is_valid = confirmation_manager.validate_and_consume(
            confirmation_id=confirmation_id.strip(),
            tool_name="capture_screenshot",
            arguments=action_args,
        )
        if not is_valid:
            return ToolResult(
                success=False,
                error=(
                    f"Confirmation token '{confirmation_id}' is invalid, expired, or has not been approved yet. "
                    "Please approve the confirmation or request a new one."
                ),
            )
    else:
        pending = confirmation_manager.create_pending_action(
            tool_name="capture_screenshot",
            arguments=action_args,
            description="Capture primary display screenshot and save to local disk.",
        )
        return ToolResult(
            success=False,
            error=(
                "Confirmation required: Capturing a screenshot requires user approval. "
                f"Please confirm this action with confirmation_id '{pending.confirmation_id}'."
            ),
            output={
                "requires_confirmation": True,
                "confirmation_id": pending.confirmation_id,
                "action": "capture_screenshot",
            },
        )

    # Perform local screenshot capture
    try:
        settings.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        img = _grab_primary_display()

        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp_str}.png"
        target_path = settings.SCREENSHOTS_DIR / filename

        img.save(target_path, format="PNG")

        file_size_bytes = target_path.stat().st_size
        width, height = img.size

        return ToolResult(
            success=True,
            output={
                "filename": filename,
                "saved_path": str(target_path),
                "dimensions": f"{width}x{height}",
                "size_bytes": file_size_bytes,
                "local_only": True,
                "summary": (
                    f"Screenshot captured and stored locally: {filename} "
                    f"({width}x{height}, {round(file_size_bytes / 1024, 1)} KB). "
                    "Not transmitted to external APIs."
                ),
            },
        )
    except RuntimeError as e:
        return ToolResult(
            success=False,
            error=str(e),
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Unexpected error while taking screenshot: {str(e)}",
        )


def analyze_screenshot(
    screenshot_filename: str,
    prompt: str = "Describe what is shown in this screenshot.",
    confirmation_id: Optional[str] = None,
) -> ToolResult:
    """
    Analyze a previously captured local screenshot using Gemini multimodal vision.
    Requires explicit confirmation disclosing that local image data will be transmitted externally.
    
    Args:
        screenshot_filename: Filename of the locally saved screenshot in the screenshots directory.
        prompt: Optional analytical question or instruction for the vision model.
        confirmation_id: Optional confirmation token if confirmation was already approved.
    """
    try:
        verify_windows_os("analyze_screenshot")
    except UnsupportedPlatformError as e:
        return ToolResult(success=False, error=str(e))

    if not isinstance(screenshot_filename, str) or not screenshot_filename.strip():
        return ToolResult(
            success=False,
            error="Argument 'screenshot_filename' is required.",
        )

    clean_filename = Path(screenshot_filename.strip()).name
    action_args = {"screenshot_filename": clean_filename, "prompt": prompt.strip()}

    # Resolve safe local path inside screenshots dir
    try:
        safe_path = resolve_safe_path(
            base_dir=settings.SCREENSHOTS_DIR,
            user_path=clean_filename,
            allow_root=False,
            must_exist=True,
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Screenshot file error: {str(e)}")

    # Confirmation requirement: explicitly disclose external API transmission
    if confirmation_id:
        is_valid = confirmation_manager.validate_and_consume(
            confirmation_id=confirmation_id.strip(),
            tool_name="analyze_screenshot",
            arguments=action_args,
        )
        if not is_valid:
            return ToolResult(
                success=False,
                error=(
                    f"Confirmation token '{confirmation_id}' is invalid, expired, or has not been approved yet. "
                    "Please approve the confirmation or request a new one."
                ),
            )
    else:
        pending = confirmation_manager.create_pending_action(
            tool_name="analyze_screenshot",
            arguments=action_args,
            description=(
                f"Transmit local screenshot '{clean_filename}' to Google Gemini external API "
                f"for visual analysis with prompt: '{prompt}'."
            ),
        )
        return ToolResult(
            success=False,
            error=(
                f"Confirmation required: Transmitting local screenshot '{clean_filename}' to Gemini "
                f"external API for visual analysis. Please confirm this action with confirmation_id '{pending.confirmation_id}'."
            ),
            output={
                "requires_confirmation": True,
                "confirmation_id": pending.confirmation_id,
                "action": "analyze_screenshot",
                "disclosure": f"External API transmission of image {clean_filename}",
            },
        )

    # Perform analysis with Gemini
    try:
        from google.genai import types
        from app.services.agent_service import agent_service

        client = agent_service._get_client()
        image_bytes = safe_path.read_bytes()

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        text_part = types.Part.from_text(text=prompt)

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[types.Content(parts=[image_part, text_part])],
        )

        return ToolResult(
            success=True,
            output={
                "filename": clean_filename,
                "analysis": response.text or "No textual analysis produced.",
                "external_api_used": "Gemini Multimodal",
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Screenshot analysis failed: {str(e)}",
        )
