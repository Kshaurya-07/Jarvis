import datetime
import json
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.confirmation import confirmation_manager
from app.tools.base import ToolResult


class Reminder(BaseModel):
    """Model representing a locally stored reminder."""
    id: str
    title: str
    due_time: str
    notes: Optional[str] = None
    completed: bool = False
    created_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None


class RemindersStorage:
    """Thread-safe, local JSON storage manager for user reminders."""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or settings.REMINDERS_FILE

    def _load_raw(self) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_raw(self, reminders: List[Dict[str, Any]]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(reminders, f, indent=2, ensure_ascii=False)

    def list_all(self, include_completed: bool = False) -> List[Reminder]:
        raw = self._load_raw()
        results: List[Reminder] = []
        for item in raw:
            try:
                rem = Reminder(**item)
                if include_completed or not rem.completed:
                    results.append(rem)
            except Exception:
                continue
        return results

    def get_by_id(self, reminder_id: str) -> Optional[Reminder]:
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == reminder_id:
                try:
                    return Reminder(**item)
                except Exception:
                    return None
        return None

    def add(self, title: str, due_time: str, notes: Optional[str] = None) -> Reminder:
        raw = self._load_raw()
        new_id = f"rem_{secrets.token_hex(4)}"
        reminder = Reminder(
            id=new_id,
            title=title.strip(),
            due_time=due_time.strip(),
            notes=notes.strip() if notes else None,
            completed=False,
        )
        raw.append(reminder.model_dump())
        self._save_raw(raw)
        return reminder

    def complete(self, reminder_id: str) -> Optional[Reminder]:
        raw = self._load_raw()
        found = None
        for item in raw:
            if item.get("id") == reminder_id:
                item["completed"] = True
                item["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                found = Reminder(**item)
                break
        if found:
            self._save_raw(raw)
        return found

    def delete(self, reminder_id: str) -> bool:
        raw = self._load_raw()
        initial_len = len(raw)
        filtered = [item for item in raw if item.get("id") != reminder_id]
        if len(filtered) < initial_len:
            self._save_raw(filtered)
            return True
        return False


reminders_storage = RemindersStorage()

DISCLAIMER_TEXT = (
    "Note: Reminders are stored in your Jarvis cloud account and shown when you open the app. "
    "There are no push notifications yet — check the app for what's due."
)


def create_reminder(title: str, due_time: str, notes: Optional[str] = None, user=None) -> ToolResult:
    """
    Create and store a local reminder on the laptop.
    
    Args:
        title: Short title or subject of the reminder.
        due_time: When the reminder is due (e.g. 'Tomorrow at 10 AM', '2026-11-10 14:00').
        notes: Optional extra details or context.
    """
    if not isinstance(title, str) or not title.strip():
        return ToolResult(success=False, error="Argument 'title' is required and must be non-empty.")
    if not isinstance(due_time, str) or not due_time.strip():
        return ToolResult(success=False, error="Argument 'due_time' is required and must be non-empty.")

    try:
        from app.core.store import get_user_store
        from app.core.user_context import get_current_user, resolve_user

        u = resolve_user(user or get_current_user())
        reminder = get_user_store().add_reminder(
            u, title=title, due_time=due_time, notes=str(notes) if notes else None
        )
        return ToolResult(
            success=True,
            output={
                "reminder": reminder,
                "notice": DISCLAIMER_TEXT,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to save reminder: {str(e)}")


def list_reminders(include_completed: bool = False, user=None) -> ToolResult:
    """
    List local reminders.
    
    Args:
        include_completed: Whether to include already completed reminders (default False).
    """
    try:
        from app.core.store import get_user_store
        from app.core.user_context import get_current_user, resolve_user

        u = resolve_user(user or get_current_user())
        reminders = get_user_store().list_reminders(u, include_completed=include_completed)
        return ToolResult(
            success=True,
            output={
                "count": len(reminders),
                "reminders": reminders,
                "notice": DISCLAIMER_TEXT,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to list reminders: {str(e)}")


def complete_reminder(reminder_id: str, user=None) -> ToolResult:
    """
    Mark a local reminder as completed.
    
    Args:
        reminder_id: The unique ID of the reminder (e.g. 'rem_1a2b3c4d').
    """
    if not isinstance(reminder_id, str) or not reminder_id.strip():
        return ToolResult(success=False, error="Argument 'reminder_id' is required.")

    clean_id = reminder_id.strip()
    try:
        from app.core.store import get_user_store
        from app.core.user_context import get_current_user, resolve_user

        u = resolve_user(user or get_current_user())
        reminder = get_user_store().complete_reminder(u, clean_id)
        if not reminder:
            return ToolResult(success=False, error=f"Reminder with ID '{clean_id}' was not found.")
        return ToolResult(
            success=True,
            output={
                "message": f"Reminder '{reminder['title']}' marked as completed.",
                "reminder": reminder,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to complete reminder: {str(e)}")


def delete_reminder(reminder_id: str, confirmation_id: Optional[str] = None, user=None) -> ToolResult:
    """
    Delete a local reminder. Requires explicit confirmation before deletion.
    
    Args:
        reminder_id: The unique ID of the reminder to delete.
        confirmation_id: Optional confirmation token if already approved.
    """
    if not isinstance(reminder_id, str) or not reminder_id.strip():
        return ToolResult(success=False, error="Argument 'reminder_id' is required.")

    from app.core.store import get_user_store
    from app.core.user_context import get_current_user, resolve_user

    u = resolve_user(user or get_current_user())
    clean_id = reminder_id.strip()
    reminder = get_user_store().get_reminder(u, clean_id)
    if not reminder:
        return ToolResult(success=False, error=f"Reminder with ID '{clean_id}' was not found.")

    action_args = {"reminder_id": clean_id}

    if confirmation_id:
        is_valid = confirmation_manager.validate_and_consume(
            confirmation_id=confirmation_id.strip(),
            tool_name="delete_reminder",
            arguments=action_args,
            user=u,
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
            tool_name="delete_reminder",
            arguments=action_args,
            description=f"Delete reminder '{reminder['title']}' ({clean_id})",
            user=u,
        )
        return ToolResult(
            success=False,
            error=(
                f"Confirmation required: Deleting reminder '{reminder['title']}' cannot be undone. "
                f"Please confirm this action with confirmation_id '{pending.confirmation_id}'."
            ),
            output={
                "requires_confirmation": True,
                "confirmation_id": pending.confirmation_id,
                "action": "delete_reminder",
                "reminder_id": clean_id,
                "title": reminder["title"],
            },
        )

    # Perform deletion
    deleted = get_user_store().delete_reminder(u, clean_id)
    if deleted:
        return ToolResult(
            success=True,
            output={
                "message": f"Reminder '{reminder['title']}' ({clean_id}) was successfully deleted.",
                "reminder_id": clean_id,
            },
        )
    return ToolResult(success=False, error=f"Failed to delete reminder '{clean_id}'.")
