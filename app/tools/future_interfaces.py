"""
Future Tool Interfaces and Architectural Placeholders for Jarvis.

NOTE: None of these tools are currently functional in Phase 1.
They define clean interfaces and architectural contracts for future phases.
Jarvis will never claim or pretend these features are active until implemented.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class FutureFeatureNotImplementedError(NotImplementedError):
    """Raised when a future, unactivated feature interface is called."""
    pass


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
        """TODO [Phase 2]: Retrieve structured page text or DOM of the active tab."""
        raise FutureFeatureNotImplementedError("Browser extension integration is planned for a future phase.")

    @abstractmethod
    async def click_element(self, selector: str) -> bool:
        """TODO [Phase 2]: Click an element with user confirmation."""
        raise FutureFeatureNotImplementedError("Browser element interaction is planned for a future phase.")


class VisionLaptopControlInterface(ABC):
    """
    Interface for screenshot understanding and visible laptop control.
    
    Security Contract:
    - Never perform arbitrary shell command execution.
    - Always display visible indicators when screen capture is active.
    - Prompt for user confirmation prior to any destructive action.
    """

    @abstractmethod
    async def capture_screen(self, region: Optional[Dict[str, int]] = None) -> bytes:
        """TODO [Phase 2]: Capture screen buffer for multimodal analysis."""
        raise FutureFeatureNotImplementedError("Screenshot understanding is planned for a future phase.")

    @abstractmethod
    async def perform_click(self, x: int, y: int) -> bool:
        """TODO [Phase 2]: Visible pointer action with confirmation."""
        raise FutureFeatureNotImplementedError("Laptop UI control is planned for a future phase.")


class VoiceIOInterface(ABC):
    """
    Interface for voice input (speech-to-text) and output (text-to-speech).
    """

    @abstractmethod
    async def listen_for_command(self) -> str:
        """TODO [Phase 3]: Capture audio from microphone and transcribe to text."""
        raise FutureFeatureNotImplementedError("Voice input is planned for a future phase.")

    @abstractmethod
    async def speak(self, text: str) -> None:
        """TODO [Phase 3]: Synthesize text to speech using local or cloud TTS."""
        raise FutureFeatureNotImplementedError("Voice output is planned for a future phase.")


class WebSearchInterface(ABC):
    """
    Interface for live web search and information retrieval.
    """

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """TODO [Phase 2]: Perform web search via approved search provider."""
        raise FutureFeatureNotImplementedError("Web search is planned for a future phase.")


class RemindersInterface(ABC):
    """
    Interface for user reminders and scheduled notifications.
    """

    @abstractmethod
    async def set_reminder(self, title: str, timestamp_iso: str) -> Dict[str, Any]:
        """TODO [Phase 2]: Schedule a user reminder."""
        raise FutureFeatureNotImplementedError("Reminders are planned for a future phase.")

    @abstractmethod
    async def list_reminders(self) -> List[Dict[str, Any]]:
        """TODO [Phase 2]: List upcoming reminders."""
        raise FutureFeatureNotImplementedError("Reminders are planned for a future phase.")


class MemoryInterface(ABC):
    """
    Interface for persistent memory with user-controlled storage, inspection, and deletion.
    
    Security Contract:
    - Never store passwords, cookies, or secrets.
    - User must have complete control to list and purge memories at any time.
    """

    @abstractmethod
    async def remember(self, key: str, value: str) -> bool:
        """TODO [Phase 2]: Save long-term memory."""
        raise FutureFeatureNotImplementedError("Memory storage is planned for a future phase.")

    @abstractmethod
    async def recall(self, query: str) -> List[Dict[str, str]]:
        """TODO [Phase 2]: Recall relevant memory items."""
        raise FutureFeatureNotImplementedError("Memory recall is planned for a future phase.")

    @abstractmethod
    async def delete_memory(self, memory_id: str) -> bool:
        """TODO [Phase 2]: User-controlled memory deletion."""
        raise FutureFeatureNotImplementedError("Memory deletion is planned for a future phase.")


class GoogleWorkspaceInterface(ABC):
    """
    Interface for Gmail and Google Calendar integrations using official OAuth 2.0 flows.
    
    Security Contract:
    - Use strict, least-privilege OAuth scopes.
    - Require user confirmation before sending emails or modifying calendar events.
    """

    @abstractmethod
    async def list_unread_emails(self, max_count: int = 10) -> List[Dict[str, Any]]:
        """TODO [Phase 3]: Fetch unread email summaries via Gmail API."""
        raise FutureFeatureNotImplementedError("Gmail integration is planned for a future phase.")

    @abstractmethod
    async def list_calendar_events(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """TODO [Phase 3]: Fetch upcoming calendar events via Google Calendar API."""
        raise FutureFeatureNotImplementedError("Google Calendar integration is planned for a future phase.")
