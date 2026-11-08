import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings

# Setup standard application logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
app_logger = logging.getLogger("jarvis")


class ActionLogEntry(BaseModel):
    """Structured entry for tracking tool executions safely."""
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    tool_name: str
    status: str  # "success" or "failure"
    details: Optional[str] = None
    execution_time_ms: Optional[float] = None


class ActionLogger:
    """Records audit logs for agent actions without logging sensitive data."""

    def __init__(self, log_file: Optional[Path] = None, max_memory_entries: int = 200):
        self.log_file = log_file or settings.ACTION_LOG_FILE
        self.max_memory_entries = max_memory_entries
        self._memory_entries: List[ActionLogEntry] = []

    def record_action(
        self,
        tool_name: str,
        status: str,
        details: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
    ) -> ActionLogEntry:
        """
        Record a tool action to in-memory history and append to the action log file.
        Never log secrets or full file contents.
        """
        # Ensure details do not leak excessive length or potential secrets
        safe_details = None
        if details:
            # Truncate details if overly long
            safe_details = details[:300] if len(details) > 300 else details

        entry = ActionLogEntry(
            tool_name=tool_name,
            status=status,
            details=safe_details,
            execution_time_ms=execution_time_ms,
        )

        # Store in memory
        self._memory_entries.append(entry)
        if len(self._memory_entries) > self.max_memory_entries:
            self._memory_entries.pop(0)

        # Append to disk log file
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            app_logger.warning("Failed to write to action log file: %s", e)

        app_logger.info(
            "Action: %s | Status: %s | Time: %sms | Details: %s",
            tool_name,
            status,
            f"{execution_time_ms:.1f}" if execution_time_ms is not None else "N/A",
            safe_details or "none",
        )
        return entry

    def get_recent_actions(self, limit: int = 50) -> List[ActionLogEntry]:
        """Returns the most recent in-memory action entries."""
        return self._memory_entries[-limit:]


# Global instance
action_logger = ActionLogger()
