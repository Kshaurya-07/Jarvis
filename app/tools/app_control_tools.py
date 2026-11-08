import subprocess
import sys
from typing import Any, Dict, Optional

from app.core.confirmation import confirmation_manager
from app.core.security import verify_windows_os, UnsupportedPlatformError
from app.tools.base import ToolResult

# Server-side allowlist strictly mapping permitted app keys to executables
ALLOWED_APPLICATIONS: Dict[str, Dict[str, str]] = {
    "notepad": {
        "display_name": "Notepad",
        "executable": "notepad.exe",
        "description": "Windows standard text editor",
    },
    "calculator": {
        "display_name": "Calculator",
        "executable": "calc.exe",
        "description": "Windows Calculator",
    },
    "paint": {
        "display_name": "Paint",
        "executable": "mspaint.exe",
        "description": "Windows Paint graphics editor",
    },
    "explorer": {
        "display_name": "File Explorer",
        "executable": "explorer.exe",
        "description": "Windows File Explorer",
    },
    "cmd": {
        "display_name": "Command Prompt",
        "executable": "cmd.exe",
        "description": "Windows Command Prompt (opens interactive window only)",
    },
}


def open_application(app_name: str, confirmation_id: Optional[str] = None) -> ToolResult:
    """
    Open an application from the server-side allowlist on Windows.
    Requires an explicit user confirmation step before launching.
    
    Args:
        app_name: The key of the allowed application (e.g. 'notepad', 'calculator', 'paint', 'explorer', 'cmd').
        confirmation_id: Optional confirmation token if confirmation was already granted.
    """
    try:
        verify_windows_os("open_application")
    except UnsupportedPlatformError as e:
        return ToolResult(success=False, error=str(e))

    if not isinstance(app_name, str) or not app_name.strip():
        return ToolResult(
            success=False,
            error="Argument 'app_name' is required and must be a non-empty string.",
        )

    app_key = app_name.strip().lower()

    if app_key not in ALLOWED_APPLICATIONS:
        allowed_list = ", ".join(sorted(ALLOWED_APPLICATIONS.keys()))
        return ToolResult(
            success=False,
            error=(
                f"Application '{app_name}' is not in the server-side allowlist. "
                f"Approved applications for Phase 2: {allowed_list}."
            ),
        )

    app_config = ALLOWED_APPLICATIONS[app_key]
    action_args = {"app_name": app_key}

    # Confirmation enforcement
    if confirmation_id:
        is_valid = confirmation_manager.validate_and_consume(
            confirmation_id=confirmation_id.strip(),
            tool_name="open_application",
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
        # Generate pending action and pause execution
        pending = confirmation_manager.create_pending_action(
            tool_name="open_application",
            arguments=action_args,
            description=f"Launch application '{app_config['display_name']}' ({app_config['executable']})",
        )
        return ToolResult(
            success=False,
            error=(
                f"Confirmation required: Opening '{app_config['display_name']}' modifies system state. "
                f"Please confirm this action with confirmation_id '{pending.confirmation_id}'."
            ),
            output={
                "requires_confirmation": True,
                "confirmation_id": pending.confirmation_id,
                "action": "open_application",
                "app_name": app_key,
                "display_name": app_config["display_name"],
            },
        )

    # Launch application without shell interpretation
    try:
        proc = subprocess.Popen([app_config["executable"]], shell=False)
        return ToolResult(
            success=True,
            output={
                "message": f"Successfully launched {app_config['display_name']}.",
                "app_name": app_key,
                "executable": app_config["executable"],
                "pid": proc.pid,
            },
        )
    except FileNotFoundError:
        return ToolResult(
            success=False,
            error=f"Executable '{app_config['executable']}' was not found on this system.",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to open '{app_config['display_name']}': {str(e)}",
        )
