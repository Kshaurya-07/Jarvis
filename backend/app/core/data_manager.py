"""User data controls (Phase 12): export, wipe, backups — all per-user.

* Export / wipe work in both backends through the active UserStore.
* File backups (checksum-verified JSON snapshots in ``backups/``) are a
  **local-mode-only** feature: on Vercel the data already lives in
  Postgres (which has its own backups — see README), so
  create/list/restore raise a clear error in Postgres mode instead of
  pretending a file snapshot exists.
* In cloud mode ``get_data_locations`` never returns absolute server
  filesystem paths — only scoped, relative labels.
"""
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import __version__
from app.core.config import settings
from app.core.logger import app_logger
from app.core.security import sanitize_filename, resolve_safe_path
from app.core.store import get_user_store, uses_postgres
from app.core.user_context import UserIdentity, get_current_user, resolve_user, user_paths
from app.tools.memory_tools import MemoryItem
from app.tools.reminders_tools import Reminder


class UserDataManager:
    """
    Manages user data controls, secure export, data wiping,
    and opt-in local backup and recovery workflows.
    """

    def _u(self, user=None) -> UserIdentity:
        return resolve_user(user or get_current_user())

    def get_data_locations(self, user=None) -> Dict[str, Any]:
        """Return storage locations for the caller's own data."""
        u = self._u(user)
        store = get_user_store()
        paths = user_paths(u)
        notes = store.list_notes(u)
        reminders = store.list_reminders(u, include_completed=True)
        memories = store.list_memories(u)
        if uses_postgres():
            label = lambda name: f"Postgres (Neon) — your account's {name}"
            locs = {
                "notes": {"path": label("notes"), "description": "Your notes, stored in Postgres.", "items_count": len(notes)},
                "reminders": {"path": label("reminders"), "description": "Your reminders, stored in Postgres.", "items_count": len(reminders)},
                "memories": {"path": label("memories"), "description": "Your memories, stored in Postgres.", "items_count": len(memories)},
                "chat_history": {"path": label("chat history"), "description": "Your chat history, stored in Postgres.", "items_count": len(store.list_chat(u, limit=1000))},
            }
            return {
                "locations": locs,
                "oauth_storage": {"google": {"connected": False, "note": "Sign-in is per Google account; Gmail/Calendar read-only access is not available in cloud mode yet."}},
                "disclosure": (
                    "Your data lives in your own rows in Postgres (Neon), namespaced by your "
                    "Google account. Nothing is shared with other users. Jarvis includes zero "
                    "telemetry and zero background sync daemons."
                ),
            }

        notes_count = len(notes)
        screenshots_count = len(list(paths.screenshots_dir.glob("*.png"))) if paths.screenshots_dir.exists() else 0
        backups_count = len(list(paths.backups_dir.glob("*.json"))) if paths.backups_dir.exists() else 0
        from app.core.google_auth import google_auth_manager

        google_status = google_auth_manager.get_status()
        return {
            "locations": {
                "workspace_directory": {"path": str(paths.workspace_dir), "description": "Your sandboxed workspace folder.", "items_count": 0},
                "notes_directory": {"path": str(paths.notes_dir), "description": "Your markdown notes.", "items_count": notes_count},
                "screenshots_directory": {"path": str(paths.screenshots_dir), "description": "Your PNG screenshots.", "items_count": screenshots_count},
                "reminders_file": {"path": str(paths.reminders_file), "description": "Your reminders.", "items_count": len(reminders)},
                "memories_file": {"path": str(paths.memories_file), "description": "Your memories.", "items_count": len(memories)},
                "action_log_file": {"path": str(paths.action_log_file), "description": "Your audit log (secrets scrubbed)."},
                "backups_directory": {"path": str(paths.backups_dir), "description": "Your backup snapshots.", "items_count": backups_count},
            },
            "oauth_storage": {
                "google": {
                    "connected": google_status.get("connected", False),
                    "account_email": google_status.get("account_email"),
                    "storage_backend": google_status.get("storage_backend"),
                    "note": "Tokens are securely managed by OS Credential Locker / keyring. Disconnecting erases local tokens.",
                }
            },
            "disclosure": (
                "Your data is stored under your own account namespace. "
                "Jarvis includes zero telemetry, zero background sync daemons, and zero automatic cloud backups."
            ),
        }

    def export_user_data(self, user=None) -> Dict[str, Any]:
        """
        Export the caller's own notes, memories, and reminders in clean JSON.
        Strictly excludes secrets, API keys, and credentials.
        """
        u = self._u(user)
        store = get_user_store()
        notes = store.list_notes(u)
        reminders = store.list_reminders(u, include_completed=True)
        memories = store.list_memories(u)
        return {
            "export_format_version": "1.0",
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "app_version": __version__,
            "data": {"notes": notes, "reminders": reminders, "memories": memories},
            "summary": {
                "notes_count": len(notes),
                "reminders_count": len(reminders),
                "memories_count": len(memories),
            },
            "privacy_notice": "Secrets, credentials, and API keys are strictly excluded from user data exports.",
        }

    def clear_all_local_data(self, confirm: bool, confirmation_text: str, user=None) -> Dict[str, Any]:
        """
        Permanently wipe the caller's own notes, memories, reminders, and
        screenshots. Requires confirm=true and confirmation_text='DELETE ALL DATA'.
        """
        u = self._u(user)
        if not confirm or confirmation_text.strip().upper() != "DELETE ALL DATA":
            raise ValueError(
                "Confirmation required: To permanently clear all your data, you must pass "
                "confirm=true and confirmation_text='DELETE ALL DATA'. "
                "This will permanently delete your notes, local memories, reminders, "
                "and screenshot files. Your Gemini key and Google sign-in are preserved."
            )
        deleted = get_user_store().clear_all_user_data(u)
        return {
            "status": "cleared",
            "message": "Your data was successfully cleared.",
            "deleted_items": {
                "notes": deleted.get("notes", 0),
                "reminders": deleted.get("reminders", 0),
                "memories": deleted.get("memories", 0),
                "screenshots": deleted.get("screenshots", 0),
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def _compute_checksum(self, data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash over canonical JSON representation of data."""
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def _require_file_backups(self) -> None:
        if uses_postgres():
            raise ValueError(
                "File backups are not available in cloud mode: your data already lives in "
                "Postgres (Neon), which provides its own backups. Use Export to download "
                "a copy of your data instead."
            )

    def create_backup(self, backup_name: Optional[str] = None, user=None) -> Dict[str, Any]:
        """Create a validated local backup snapshot (local mode only)."""
        self._require_file_backups()
        u = self._u(user)
        paths = user_paths(u)
        export = self.export_user_data(u)
        data_payload = export["data"]
        checksum = self._compute_checksum(data_payload)

        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        if backup_name and backup_name.strip():
            safe_name = sanitize_filename(backup_name)
            filename = f"jarvis_backup_{safe_name}.json"
        else:
            filename = f"jarvis_backup_{timestamp_str}.json"

        paths.backups_dir.mkdir(parents=True, exist_ok=True)
        backup_file = paths.backups_dir / filename

        backup_content = {
            "jarvis_backup_version": "1.0",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "app_version": __version__,
            "includes": ["notes", "reminders", "memories"],
            "data": data_payload,
            "checksum": checksum,
            "privacy_notice": "User-owned content only. Secrets, API keys, and credentials are strictly excluded.",
        }

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_content, f, indent=2)

        return {
            "status": "created",
            "backup_filename": filename,
            "backup_path": str(backup_file),
            "created_at": backup_content["created_at"],
            "checksum": checksum,
            "summary": export["summary"],
        }

    def validate_backup_content(self, backup_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate backup structure, version, checksum integrity, and sanitize filenames.
        Raises ValueError if validation fails.
        """
        if not isinstance(backup_dict, dict):
            raise ValueError("Invalid backup: root content must be a JSON object.")

        if backup_dict.get("jarvis_backup_version") != "1.0":
            raise ValueError(
                f"Unsupported backup version '{backup_dict.get('jarvis_backup_version')}'. Supported: '1.0'."
            )

        data = backup_dict.get("data")
        if not isinstance(data, dict):
            raise ValueError("Invalid backup: missing 'data' object.")

        # Checksum validation
        expected_checksum = backup_dict.get("checksum")
        if not expected_checksum:
            raise ValueError("Invalid backup: missing 'checksum' attribute.")

        computed_checksum = self._compute_checksum(data)
        if computed_checksum != expected_checksum:
            raise ValueError(
                f"Backup checksum mismatch! Integrity check failed. "
                f"Expected: {expected_checksum[:12]}..., Computed: {computed_checksum[:12]}..."
            )

        # Validate notes entries
        notes = data.get("notes", [])
        if not isinstance(notes, list):
            raise ValueError("Invalid backup: 'notes' must be a list.")
        for idx, note in enumerate(notes):
            if not isinstance(note, dict) or "filename" not in note or "content" not in note:
                raise ValueError(f"Invalid note at index {idx}: must have 'filename' and 'content'.")
            # Enforce path traversal defense inside backup filenames
            fname = note["filename"]
            if ".." in fname or "/" in fname or "\\" in fname:
                raise ValueError(f"Security violation in backup note filename: '{fname}' attempts path traversal.")
            if not fname.endswith(".md"):
                raise ValueError(f"Security violation in backup note filename: '{fname}' is not a markdown file.")

        # Validate reminders entries
        reminders = data.get("reminders", [])
        if not isinstance(reminders, list):
            raise ValueError("Invalid backup: 'reminders' must be a list.")
        for idx, rem in enumerate(reminders):
            if not isinstance(rem, dict) or "id" not in rem or "title" not in rem:
                raise ValueError(f"Invalid reminder at index {idx}: must contain 'id' and 'title'.")

        # Validate memories entries
        memories = data.get("memories", [])
        if not isinstance(memories, list):
            raise ValueError("Invalid backup: 'memories' must be a list.")
        for idx, mem in enumerate(memories):
            if not isinstance(mem, dict) or "key" not in mem or "content" not in mem:
                raise ValueError(f"Invalid memory at index {idx}: must contain 'key' and 'content'.")

        return backup_dict

    def restore_backup(
        self,
        backup_filename: str,
        confirm_overwrite: bool = False,
        user=None,
    ) -> Dict[str, Any]:
        """
        Safely restore the caller's data from a local backup file after
        checksum validation (local mode only).
        Requires confirm_overwrite=true if existing data is present.
        """
        self._require_file_backups()
        u = self._u(user)
        paths = user_paths(u)
        store = get_user_store()
        # Resolve path safely inside backups directory
        backup_path = resolve_safe_path(paths.backups_dir, backup_filename, must_exist=True)

        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_dict = json.load(f)
        except Exception as e:
            raise ValueError(f"Could not read backup file '{backup_filename}': {e}") from e

        # Validate content & checksum
        validated = self.validate_backup_content(backup_dict)
        data = validated["data"]

        # Check existing data
        has_existing_notes = bool(store.list_notes(u))
        has_existing_reminders = bool(store.list_reminders(u, include_completed=True))
        has_existing_memories = bool(store.list_memories(u))

        if (has_existing_notes or has_existing_reminders or has_existing_memories) and not confirm_overwrite:
            raise ValueError(
                "Existing local data found (notes, reminders, or memories). "
                "Restoring this backup will overwrite existing records. "
                "Pass confirm_overwrite=true to confirm and proceed."
            )

        # Restore notes (overwrite by filename: the target file is written
        # in place, so a restored note replaces any existing same-name note)
        restored_notes = 0
        for note in data.get("notes", []):
            safe_fname = sanitize_filename(Path(note["filename"]).stem) + ".md"
            target_file = paths.notes_dir / safe_fname
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(note["content"], encoding="utf-8")
            restored_notes += 1

        # Restore reminders: with confirm_overwrite, clear the existing
        # reminders first — otherwise every restore duplicates them.
        if confirm_overwrite:
            for existing in store.list_reminders(u, include_completed=True):
                store.delete_reminder(u, existing["id"])
        reminders_list = [Reminder(**r) for r in data.get("reminders", [])]
        for r in reminders_list:
            store.add_reminder(u, title=r.title, due_time=r.due_time, notes=r.notes)

        # Restore memories
        store.clear_memories(u)
        restored_memories = 0
        for m in data.get("memories", []):
            item = MemoryItem(**m)
            store.put_memory(u, item.key, item.content)
            restored_memories += 1

        return {
            "status": "restored",
            "message": f"Successfully restored backup '{backup_filename}'.",
            "restored_items": {
                "notes": restored_notes,
                "reminders": len(reminders_list),
                "memories": restored_memories,
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def list_backups(self, user=None) -> List[Dict[str, Any]]:
        """List the caller's local backups with metadata (local mode only)."""
        self._require_file_backups()
        u = self._u(user)
        paths = user_paths(u)
        if not paths.backups_dir.exists():
            return []

        results: List[Dict[str, Any]] = []
        for b_file in sorted(paths.backups_dir.glob("*.json"), reverse=True):
            info = {
                "filename": b_file.name,
                "size_bytes": b_file.stat().st_size,
                "created_at": datetime.datetime.fromtimestamp(
                    b_file.stat().st_ctime, tz=datetime.timezone.utc
                ).isoformat(),
                "is_valid": False,
            }
            try:
                with open(b_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
                self.validate_backup_content(content)
                info["is_valid"] = True
                info["checksum"] = content.get("checksum")
                info["backup_version"] = content.get("jarvis_backup_version")
            except Exception:
                info["is_valid"] = False
            results.append(info)

        return results


# Global singleton instance
user_data_manager = UserDataManager()
