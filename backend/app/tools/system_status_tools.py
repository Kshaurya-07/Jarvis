import re

import psutil

from app.core.config import settings
from app.core.security import verify_windows_os, UnsupportedPlatformError

_CLOUD_MSG = (
    "System status is a local-only feature: it reads a physical laptop's battery, "
    "disk and RAM, which a cloud server does not have. Not available in cloud mode."
)
from app.tools.base import ToolResult


def get_battery_status() -> ToolResult:
    if settings.CLOUD_MODE:
        return ToolResult(success=False, error=_CLOUD_MSG)
    """
    Retrieve current battery status, charge level, and power source.
    Read-only hardware status tool.
    """
    try:
        verify_windows_os("get_battery_status")
    except UnsupportedPlatformError as e:
        return ToolResult(success=False, error=str(e))

    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return ToolResult(
                success=True,
                output={
                    "battery_present": False,
                    "summary": "No battery detected (system is operating on desktop AC power).",
                },
            )

        plugged = battery.power_plugged
        percent = round(battery.percent, 1)

        if plugged:
            status_desc = "plugged in (charging / full)"
            time_str = "Unlimited (AC connected)"
        elif battery.secsleft and battery.secsleft > 0:
            hours, remainder = divmod(battery.secsleft, 3600)
            minutes, _ = divmod(remainder, 60)
            status_desc = "discharging (on battery)"
            time_str = f"~{hours}h {minutes}m remaining"
        else:
            status_desc = "discharging (on battery)"
            time_str = "Calculating remaining time"

        summary = f"Battery: {percent}% | Power: {status_desc} | Estimated time: {time_str}"

        return ToolResult(
            success=True,
            output={
                "battery_present": True,
                "percent": percent,
                "power_plugged": plugged,
                "time_remaining": time_str,
                "summary": summary,
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Unable to retrieve battery status: {str(e)}",
        )


def get_storage_status(drive: str = "C:") -> ToolResult:
    if settings.CLOUD_MODE:
        return ToolResult(success=False, error=_CLOUD_MSG)
    """
    Retrieve disk storage status for a specified drive.
    Read-only storage status tool.
    
    Args:
        drive: Drive letter or mount point (defaults to 'C:').
    """
    try:
        verify_windows_os("get_storage_status")
    except UnsupportedPlatformError as e:
        return ToolResult(success=False, error=str(e))

    if not isinstance(drive, str) or not drive.strip():
        drive = "C:"

    clean_drive = drive.strip().upper()
    # Validate drive format: e.g. "C:", "C:\", "D:"
    if not re.match(r"^[A-Z]:[/\\]?$", clean_drive):
        return ToolResult(
            success=False,
            error=f"Invalid drive specification '{drive}'. Expected format like 'C:' or 'D:'.",
        )

    # Ensure trailing slash for Windows disk_usage
    lookup_path = f"{clean_drive[:2]}\\"

    try:
        usage = psutil.disk_usage(lookup_path)
        total_gb = round(usage.total / (1024 ** 3), 1)
        used_gb = round(usage.used / (1024 ** 3), 1)
        free_gb = round(usage.free / (1024 ** 3), 1)
        percent_used = round(usage.percent, 1)

        summary = (
            f"Drive {clean_drive[:2]} Storage: {free_gb} GB free of {total_gb} GB total "
            f"({percent_used}% used, {used_gb} GB used)"
        )

        return ToolResult(
            success=True,
            output={
                "drive": clean_drive[:2],
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "percent_used": percent_used,
                "summary": summary,
            },
        )
    except FileNotFoundError:
        return ToolResult(
            success=False,
            error=f"Drive '{clean_drive[:2]}' was not found on this system.",
        )
    except PermissionError:
        return ToolResult(
            success=False,
            error=f"Permission denied accessing drive '{clean_drive[:2]}'.",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to query storage for drive '{clean_drive[:2]}': {str(e)}",
        )


def get_memory_status() -> ToolResult:
    if settings.CLOUD_MODE:
        return ToolResult(success=False, error=_CLOUD_MSG)
    """
    Retrieve current RAM (memory) usage metrics.
    Read-only system status tool.
    """
    try:
        verify_windows_os("get_memory_status")
    except UnsupportedPlatformError as e:
        return ToolResult(success=False, error=str(e))

    try:
        mem = psutil.virtual_memory()
        total_gb = round(mem.total / (1024 ** 3), 2)
        available_gb = round(mem.available / (1024 ** 3), 2)
        used_gb = round(mem.used / (1024 ** 3), 2)
        percent_used = round(mem.percent, 1)

        summary = (
            f"RAM Usage: {available_gb} GB available of {total_gb} GB total "
            f"({percent_used}% used, {used_gb} GB used)"
        )

        return ToolResult(
            success=True,
            output={
                "total_gb": total_gb,
                "available_gb": available_gb,
                "used_gb": used_gb,
                "percent_used": percent_used,
                "summary": summary,
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to query system memory: {str(e)}",
        )
