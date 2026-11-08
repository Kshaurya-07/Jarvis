import datetime
import json
import logging
import re
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

# Sensitive data redaction patterns for audit log entries
REDACTION_PATTERNS = [
    (re.compile(r"(?i)(?:password|passwd|pwd|secret|token|api_key)\s*[:=]\s*\S+"), "[REDACTED_SECRET]"),
    (re.compile(r"(?:AIza[0-9A-Za-z-_]{35}|sk-[a-zA-Z0-9]{20,}|gh[pousr]_[a-zA-Z0-9]{20,}|tvly-[a-zA-Z0-9_-]+)"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+"), "[REDACTED_TOKEN]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED_CARD]"),
]


def scrub_sensitive_text(text: str) -> str:
    """Scrub sensitive credentials, tokens, card numbers, and emails from log strings."""
    if not text:
        return ""
    scrubbed = text
    for pattern, replacement in REDACTION_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


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
            scrubbed = scrub_sensitive_text(str(details))
            # Truncate details if overly long
            safe_details = scrubbed[:300] if len(scrubbed) > 300 else scrubbed

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
