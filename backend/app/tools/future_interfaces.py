"""
Future Tool Interfaces and Architectural Placeholders for Jarvis.

NOTE: None of these tools are currently functional.
They define clean interfaces, platform constraints, and architectural contracts for future phases.
Jarvis will never claim or pretend these features are active until implemented.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class FutureFeatureNotImplementedError(NotImplementedError):
    """Raised when a future, unactivated feature interface is called."""


class WiFiControlInterface(ABC):
    """
    Interface for Wi-Fi status inspection and network profile management.
    
    Platform & Permission Requirements (Planned for Phase 3):
    - Windows API: Native Windows WLAN API (`wlanapi.dll`) or `netsh wlan`.
    - OS Permissions: Requires Administrator or 'Network Configuration Operators' group membership
      to modify network states, connect to new SSIDs, or toggle adapter radio states.
    - Security Contract:
      * Must require explicit user confirmation before disconnecting or switching networks.
      * Must never log or store WPA2/WPA3 pre-shared keys or network credentials in plaintext or memory.
    """

    @abstractmethod
    async def get_wifi_status(self) -> Dict[str, Any]:
        """TODO [Phase 3]: Query connected SSID, signal strength, and adapter state."""
        raise FutureFeatureNotImplementedError("Wi-Fi management is planned for a future phase.")

    @abstractmethod
    async def toggle_wifi(self, enable: bool) -> bool:
        """TODO [Phase 3]: Enable or disable Wi-Fi radio with explicit user confirmation."""
        raise FutureFeatureNotImplementedError("Wi-Fi control is planned for a future phase.")


class VolumeControlInterface(ABC):
    """
    Interface for Windows system audio volume and mute controls.
    
    Platform & Permission Requirements (Planned for Phase 3):
    - Windows API: Windows Core Audio APIs (`IAudioEndpointVolume` via `pycaw` / `comtypes`).
    - OS Permissions: Requires an active interactive desktop session (Session 1+).
      Fails silently or throws errors when running as a headless Windows Service (Session 0).
    - Security Contract:
      * Must clamp master volume to safe listening levels (e.g. max 100%, user-set safety cap).
      * No elevated admin rights required for standard audio endpoint adjustments.
    """

    @abstractmethod
    async def get_master_volume(self) -> float:
        """TODO [Phase 3]: Retrieve master audio volume level (0.0 to 1.0)."""
        raise FutureFeatureNotImplementedError("Volume control is planned for a future phase.")

    @abstractmethod
    async def set_master_volume(self, level: float) -> bool:
        """TODO [Phase 3]: Adjust master audio volume with user confirmation."""
        raise FutureFeatureNotImplementedError("Volume control is planned for a future phase.")

    @abstractmethod
    async def toggle_mute(self) -> bool:
        """TODO [Phase 3]: Toggle master audio mute state."""
        raise FutureFeatureNotImplementedError("Volume mute control is planned for a future phase.")


class BrightnessControlInterface(ABC):
    """
    Interface for laptop display brightness adjustment.
    
    Platform & Permission Requirements (Planned for Phase 3):
    - Windows API: Windows Management Instrumentation (WMI `WmiMonitorBrightnessMethods` in root/wmi)
      or High Level Monitor Configuration APIs (`dxva2.dll`).
    - Hardware/Driver Requirements:
      * Internal laptop screens require ACPI/WMI brightness method support in display drivers.
      * External desktop monitors require DDC/CI communication over DisplayPort/HDMI/VGA.
      * Unavailable on virtual machines, remote desktop sessions, or without display driver support.
    - Security Contract:
      * Clamp brightness between 10% and 100% to prevent unreadable dark screens.
    """

    @abstractmethod
    async def get_brightness(self) -> int:
        """TODO [Phase 3]: Query current display brightness percentage."""
        raise FutureFeatureNotImplementedError("Brightness control is planned for a future phase.")

    @abstractmethod
    async def set_brightness(self, level_percent: int) -> bool:
        """TODO [Phase 3]: Adjust display brightness with confirmation."""
        raise FutureFeatureNotImplementedError("Brightness control is planned for a future phase.")


class BrowserExtensionInterface(ABC):
    """
    Interface for interacting with a user-approved active browser tab.
    
    Security Contract:
    - Must require explicit user approval for domain access.
    - Never read passwords, payment forms, or private authentication tokens.
    - Operates only in read-only DOM inspection or explicit user-confirmed form fills.
    """

    @abstractmethod
    async def get_active_tab_content(self) -> Dict[str, Any]:
        """TODO [Phase 4]: Retrieve structured page text or DOM of the active tab."""
        raise FutureFeatureNotImplementedError("Browser extension integration is planned for a future phase.")

    @abstractmethod
    async def click_element(self, selector: str) -> bool:
        """TODO [Phase 4]: Click an element with user confirmation."""
        raise FutureFeatureNotImplementedError("Browser element interaction is planned for a future phase.")


class RemindersInterface(ABC):
    """
    Interface for user reminders and scheduled notifications.
    """

    @abstractmethod
    async def set_reminder(self, title: str, timestamp_iso: str) -> Dict[str, Any]:
        """TODO [Phase 3]: Schedule a user reminder."""
        raise FutureFeatureNotImplementedError("Reminders are planned for a future phase.")

    @abstractmethod
    async def list_reminders(self) -> List[Dict[str, Any]]:
        """TODO [Phase 3]: List upcoming reminders."""
        raise FutureFeatureNotImplementedError("Reminders are planned for a future phase.")


class MemoryInterface(ABC):
    """
    Interface for persistent memory with user-controlled storage, inspection, and deletion.
    """

    @abstractmethod
    async def remember(self, key: str, value: str) -> bool:
        """TODO [Phase 3]: Save long-term memory."""
        raise FutureFeatureNotImplementedError("Memory storage is planned for a future phase.")

    @abstractmethod
    async def recall(self, query: str) -> List[Dict[str, str]]:
        """TODO [Phase 3]: Recall relevant memory items."""
        raise FutureFeatureNotImplementedError("Memory recall is planned for a future phase.")

    @abstractmethod
    async def delete_memory(self, memory_id: str) -> bool:
        """TODO [Phase 3]: User-controlled memory deletion."""
        raise FutureFeatureNotImplementedError("Memory deletion is planned for a future phase.")


class GoogleWorkspaceInterface(ABC):
    """
    Interface for Gmail and Google Calendar integrations using official OAuth 2.0 flows.
    """

    @abstractmethod
    async def list_unread_emails(self, max_count: int = 10) -> List[Dict[str, Any]]:
        """TODO [Phase 4]: Fetch unread email summaries via Gmail API."""
        raise FutureFeatureNotImplementedError("Gmail integration is planned for a future phase.")

    @abstractmethod
    async def list_calendar_events(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """TODO [Phase 4]: Fetch upcoming calendar events via Google Calendar API."""
        raise FutureFeatureNotImplementedError("Google Calendar integration is planned for a future phase.")
