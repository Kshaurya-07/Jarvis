import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.tools.base import ToolResult


class MemoryItem(BaseModel):
    """Represents an explicitly user-approved persistent memory item."""
    key: str
    content: str
    created_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


# Sensitive patterns that must NEVER be saved in memory
SENSITIVE_PATTERNS = [
    (r"(?i)\b(?:password|passwd|pwd)\b(?:\s+(?:is|was))?\s*[:=]?\s*\S+", "password or credential"),
    (r"(?i)(?:api[_-]?key|secret[_-]?key|auth[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{12,}", "API key or auth token"),
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI/API secret key"),
    (r"gh[pousr]_[a-zA-Z0-9]{20,}", "GitHub token"),
    (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{25,}", "Bearer authentication token"),
    (r"\b(?:\d{4}[ -]?){3}\d{4}\b", "payment card number"),
    (r"(?i)\bcvv\s*[:=]\s*\d{3,4}\b", "card security code"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private cryptographic key"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "Social Security Number"),
]


def detect_sensitive_data(text: str) -> Optional[str]:
    """Scan text for passwords, tokens, API keys, or financial data."""
    for pattern, description in SENSITIVE_PATTERNS:
        if re.search(pattern, text):
            return description
    return None


class MemoryStorage:
    """Local JSON storage for user-approved memories."""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or settings.MEMORIES_FILE

    def _load_raw(self) -> Dict[str, Dict[str, Any]]:
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_raw(self, memories: Dict[str, Dict[str, Any]]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2, ensure_ascii=False)

    def list_all(self) -> List[MemoryItem]:
        raw = self._load_raw()
        items: List[MemoryItem] = []
        for v in raw.values():
            try:
                items.append(MemoryItem(**v))
            except Exception:
                continue
        return sorted(items, key=lambda x: x.key)

    def get(self, key: str) -> Optional[MemoryItem]:
        raw = self._load_raw()
        clean_key = key.strip().lower()
        if clean_key in raw:
            try:
                return MemoryItem(**raw[clean_key])
            except Exception:
                return None
        return None

    def put(self, key: str, content: str) -> MemoryItem:
        raw = self._load_raw()
        clean_key = key.strip().lower()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        if clean_key in raw:
            item = MemoryItem(
                key=clean_key,
                content=content.strip(),
                created_at=raw[clean_key].get("created_at", now_iso),
                updated_at=now_iso,
            )
        else:
            item = MemoryItem(
                key=clean_key,
                content=content.strip(),
                created_at=now_iso,
                updated_at=now_iso,
            )

        raw[clean_key] = item.model_dump()
        self._save_raw(raw)
        return item

    def delete(self, key: str) -> bool:
        raw = self._load_raw()
        clean_key = key.strip().lower()
        if clean_key in raw:
            del raw[clean_key]
            self._save_raw(raw)
            return True
        return False

    def clear(self) -> int:
        raw = self._load_raw()
        count = len(raw)
        self._save_raw({})
        return count


memory_storage = MemoryStorage()


def remember_item(key: str, content: str, user=None) -> ToolResult:
    """
    Store an explicitly requested piece of information in local persistent memory.
    
    Args:
        key: A short descriptor or category (e.g. 'preferred_language', 'study_topic').
        content: The information to remember.
    """
    if not settings.MEMORY_ENABLED:
        return ToolResult(
            success=False,
            error="Memory is currently disabled by user setting. Enable memory to store items.",
        )

    if not isinstance(key, str) or not key.strip():
        return ToolResult(success=False, error="Argument 'key' is required and must be non-empty.")
    if not isinstance(content, str) or not content.strip():
        return ToolResult(success=False, error="Argument 'content' is required and must be non-empty.")

    # Sensitive data screening
    sensitive_issue = detect_sensitive_data(key) or detect_sensitive_data(content)
    if sensitive_issue:
        return ToolResult(
            success=False,
            error=(
                f"Privacy refusal: Cannot remember text containing a potential {sensitive_issue}. "
                "Jarvis strictly prohibits storing credentials, payment data, or authentication secrets."
            ),
        )

    try:
        from app.core.store import get_user_store
        from app.core.user_context import get_current_user, resolve_user

        u = resolve_user(user or get_current_user())
        item = get_user_store().put_memory(u, key=key, content=content)
        return ToolResult(
            success=True,
            output={
                "message": f"Remembered '{item['key']}'.",
                "memory": item,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to save memory: {str(e)}")


def forget_item(key: str, user=None) -> ToolResult:
    """
    Delete an item from persistent local memory.
    
    Args:
        key: The key or category of the memory to remove.
    """
    if not isinstance(key, str) or not key.strip():
        return ToolResult(success=False, error="Argument 'key' is required.")

    clean_key = key.strip().lower()
    try:
        from app.core.store import get_user_store
        from app.core.user_context import get_current_user, resolve_user

        u = resolve_user(user or get_current_user())
        deleted = get_user_store().delete_memory(u, clean_key)
        if not deleted:
            return ToolResult(
                success=False,
                error=f"No memory found with key '{clean_key}'.",
            )
        return ToolResult(
            success=True,
            output={"message": f"Successfully forgot '{clean_key}'."},
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to delete memory: {str(e)}")


def list_memories(user=None) -> ToolResult:
    """
    List all saved user-approved memory items.
    """
    if not settings.MEMORY_ENABLED:
        return ToolResult(
            success=True,
            output={
                "enabled": False,
                "count": 0,
                "memories": [],
                "notice": "Memory is currently disabled in settings.",
            },
        )

    try:
        from app.core.store import get_user_store
        from app.core.user_context import get_current_user, resolve_user

        u = resolve_user(user or get_current_user())
        items = get_user_store().list_memories(u)
        return ToolResult(
            success=True,
            output={
                "enabled": True,
                "count": len(items),
                "memories": items,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to list memories: {str(e)}")
