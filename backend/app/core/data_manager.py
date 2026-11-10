import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import __version__
from app.core.config import settings
from app.core.logger import app_logger
from app.core.security import sanitize_filename, resolve_safe_path
from app.tools.memory_tools import memory_storage, MemoryItem
from app.tools.reminders_tools import reminders_storage, Reminder


class UserDataManager:
    """
    Manages user data controls, secure export, data wiping,
    and opt-in local backup and recovery workflows.
    """

    def get_data_locations(self) -> Dict[str, Any]:
        """Return all local filesystem paths where user data is stored."""
        notes_count = len(list(settings.NOTES_DIR.glob("*.md"))) if settings.NOTES_DIR.exists() else 0
        screenshots_count = len(list(settings.SCREENSHOTS_DIR.glob("*.png"))) if settings.SCREENSHOTS_DIR.exists() else 0
        reminders_count = len(reminders_storage.list_all(include_completed=True))
        memories_count = len(memory_storage.list_all())
        backups_count = len(list(settings.BACKUPS_DIR.glob("*.json"))) if settings.BACKUPS_DIR.exists() else 0

        # OAuth token storage status
        from app.core.google_auth import google_auth_manager
        google_status = google_auth_manager.get_status()

        return {
            "locations": {
                "workspace_directory": {
                    "path": str(settings.WORKSPACE_DIR),
                    "description": "Configured sandboxed workspace folder for list_files and read_text_file.",
                },
                "notes_directory": {
                    "path": str(settings.NOTES_DIR),
                    "description": "Markdown notes directory created via create_note.",
                    "items_count": notes_count,
                },
                "screenshots_directory": {
                    "path": str(settings.SCREENSHOTS_DIR),
                    "description": "Locally stored PNG screenshots captured via capture_screenshot.",
                    "items_count": screenshots_count,
                },
                "reminders_file": {
                    "path": str(settings.REMINDERS_FILE),
                    "description": "Local JSON store for user reminders.",
                    "items_count": reminders_count,
                },
                "memories_file": {
                    "path": str(settings.MEMORIES_FILE),
                    "description": "Local JSON store for user-approved explicit memories.",
                    "items_count": memories_count,
                },
                "action_log_file": {
                    "path": str(settings.ACTION_LOG_FILE),
                    "description": "Local audit log of tool execution statuses (secrets scrubbed).",
                },
                "backups_directory": {
                    "path": str(settings.BACKUPS_DIR),
                    "description": "Opt-in local backup snapshots directory.",
                    "items_count": backups_count,
                },
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
                "All user data is stored locally on this machine in the designated directories. "
                "Jarvis includes zero telemetry, zero background sync daemons, and zero automatic cloud backups."
            ),
        }

    def export_user_data(self) -> Dict[str, Any]:
        """
        Export user-owned notes, memories, and reminders in clean JSON format.
        Strictly excludes API keys, credentials, and authentication tokens.
        """
        # Read notes
        notes: List[Dict[str, Any]] = []
        if settings.NOTES_DIR.exists():
            for note_path in sorted(settings.NOTES_DIR.glob("*.md")):
                try:
                    notes.append({
                        "filename": note_path.name,
                        "title": note_path.stem,
                        "content": note_path.read_text(encoding="utf-8"),
                        "modified_at": datetime.datetime.fromtimestamp(
                            note_path.stat().st_mtime, tz=datetime.timezone.utc
                        ).isoformat(),
                    })
                except Exception as e:
                    app_logger.warning("Could not read note '%s' during export: %s", note_path.name, e)

        # Read reminders & memories
        reminders = [r.model_dump() for r in reminders_storage.list_all(include_completed=True)]
        memories = [m.model_dump() for m in memory_storage.list_all()]

        return {
            "export_format_version": "1.0",
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "app_version": __version__,
            "data": {
                "notes": notes,
                "reminders": reminders,
                "memories": memories,
            },
            "summary": {
                "notes_count": len(notes),
                "reminders_count": len(reminders),
                "memories_count": len(memories),
            },
            "privacy_notice": "Secrets, credentials, and API keys are strictly excluded from user data exports.",
        }

    def clear_all_local_data(self, confirm: bool, confirmation_text: str) -> Dict[str, Any]:
        """
        Permanently wipe user-owned notes, memories, reminders, and screenshot images.
        Requires explicit confirmation and exact matching confirmation_text.
        """
        if not confirm or confirmation_text.strip().upper() != "DELETE ALL DATA":
            raise ValueError(
                "Confirmation required: To permanently clear all local data, you must pass "
                "confirm=true and confirmation_text='DELETE ALL DATA'. "
                "This action will permanently delete all user notes (*.md), local memories, reminders, "
                "and local screenshot files. Sandboxed workspace files and Google OAuth tokens are preserved."
            )

        deleted_notes = 0
        if settings.NOTES_DIR.exists():
            for note_path in list(settings.NOTES_DIR.glob("*.md")):
                try:
                    note_path.unlink()
                    deleted_notes += 1
                except Exception as e:
                    app_logger.warning("Failed to delete note '%s': %s", note_path, e)

        deleted_screenshots = 0
        if settings.SCREENSHOTS_DIR.exists():
            for shot_path in list(settings.SCREENSHOTS_DIR.glob("*.png")):
                try:
                    shot_path.unlink()
                    deleted_screenshots += 1
                except Exception as e:
                    app_logger.warning("Failed to delete screenshot '%s': %s", shot_path, e)

        # Clear reminders
        deleted_reminders = len(reminders_storage.list_all(include_completed=True))
        if settings.REMINDERS_FILE.exists():
            try:
                settings.REMINDERS_FILE.unlink()
            except Exception:
                pass

        # Clear memories
        deleted_memories = len(memory_storage.list_all())
        memory_storage.clear()

        return {
            "status": "cleared",
            "message": "User data successfully cleared.",
            "deleted_items": {
                "notes": deleted_notes,
                "reminders": deleted_reminders,
                "memories": deleted_memories,
                "screenshots": deleted_screenshots,
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def _compute_checksum(self, data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash over canonical JSON representation of data."""
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def create_backup(self, backup_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a validated local backup snapshot of user notes, reminders, and memories.
        Saves snapshot to backups/ directory with SHA-256 checksum integrity verification.
        Does NOT include secrets, tokens, or credentials.
        """
        export = self.export_user_data()
        data_payload = export["data"]
        checksum = self._compute_checksum(data_payload)

        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        if backup_name and backup_name.strip():
            safe_name = sanitize_filename(backup_name)
            filename = f"jarvis_backup_{safe_name}.json"
        else:
            filename = f"jarvis_backup_{timestamp_str}.json"

        settings.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        backup_file = settings.BACKUPS_DIR / filename

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
    ) -> Dict[str, Any]:
        """
        Safely restores a backup snapshot after checksum validation.
        Requires explicit confirmation before overwriting existing data.
        """
        # Resolve path safely inside backups directory
        backup_path = resolve_safe_path(settings.BACKUPS_DIR, backup_filename, must_exist=True)

        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_dict = json.load(f)
        except Exception as e:
            raise ValueError(f"Could not read backup file '{backup_filename}': {e}") from e

        # Validate content & checksum
        validated = self.validate_backup_content(backup_dict)
        data = validated["data"]

        # Check existing data
        has_existing_notes = bool(list(settings.NOTES_DIR.glob("*.md"))) if settings.NOTES_DIR.exists() else False
        has_existing_reminders = bool(reminders_storage.list_all(include_completed=True))
        has_existing_memories = bool(memory_storage.list_all())

        if (has_existing_notes or has_existing_reminders or has_existing_memories) and not confirm_overwrite:
            raise ValueError(
                "Existing local data found (notes, reminders, or memories). "
                "Restoring this backup will overwrite existing records. "
                "Pass confirm_overwrite=true to confirm and proceed."
            )

        # Restore notes
        settings.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        restored_notes = 0
        for note in data.get("notes", []):
            safe_fname = sanitize_filename(Path(note["filename"]).stem) + ".md"
            target_file = settings.NOTES_DIR / safe_fname
            target_file.write_text(note["content"], encoding="utf-8")
            restored_notes += 1

        # Restore reminders
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        reminders_list = [Reminder(**r) for r in data.get("reminders", [])]
        raw_reminders = [r.model_dump() for r in reminders_list]
        with open(settings.REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(raw_reminders, f, indent=2, ensure_ascii=False)

        # Restore memories
        memory_storage.clear()
        restored_memories = 0
        for m in data.get("memories", []):
            item = MemoryItem(**m)
            memory_storage.put(item.key, item.content)
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

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all local backups with metadata."""
        if not settings.BACKUPS_DIR.exists():
            return []

        results: List[Dict[str, Any]] = []
        for b_file in sorted(settings.BACKUPS_DIR.glob("*.json"), reverse=True):
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
