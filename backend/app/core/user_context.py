"""Per-user identity and storage scoping (Phase 12, cloud-first).

Every piece of user data — notes, memories, reminders, workspace files,
screenshots, backups, action log, chat history, encrypted Gemini key — is
namespaced by the signed-in Google account's ``sub`` claim.

* The on-disk / in-DB namespace key is ``sha256(sub)[:32]`` — an opaque
  hash, never the raw Google ID or email, so directory names and DB keys
  leak no PII.
* Local (non-cloud) mode keeps a single legacy owner identity
  (``sub="local-owner"``) that maps to the historical top-level paths
  (``workspace/``, ``notes/``, ``data/`` …), so local dev and the existing
  test suite keep working unchanged.
* The current user is carried in a :class:`contextvars.ContextVar` set by
  the ``require_user`` FastAPI dependency and read by tools, so agent tool
  calls inside a chat turn automatically operate on the right user's data
  without every tool signature changing.
"""
from __future__ import annotations

import contextvars
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import settings

LOCAL_OWNER_SUB = "local-owner"


@dataclass(frozen=True)
class UserIdentity:
    """A signed-in user (or the local owner in local mode)."""

    sub: str  # Google `sub` claim, or "local-owner"
    email: Optional[str] = None
    name: Optional[str] = None

    @property
    def is_local_owner(self) -> bool:
        return self.sub == LOCAL_OWNER_SUB

    @property
    def namespace(self) -> str:
        """Opaque, filesystem/DB-safe namespace for this user."""
        if self.is_local_owner:
            return "local-owner"
        digest = hashlib.sha256(self.sub.encode("utf-8")).hexdigest()
        return f"user_{digest[:32]}"


LOCAL_OWNER = UserIdentity(sub=LOCAL_OWNER_SUB)

_current_user: contextvars.ContextVar[Optional[UserIdentity]] = contextvars.ContextVar(
    "jarvis_current_user", default=None
)


def set_current_user(user: Optional[UserIdentity]) -> None:
    _current_user.set(user)


def get_current_user() -> Optional[UserIdentity]:
    """User for the current request/tool call, or None outside a request."""
    return _current_user.get()


def resolve_user(user: Optional[UserIdentity] = None) -> UserIdentity:
    """Explicit user, else the request contextvar, else the local owner."""
    return user or get_current_user() or LOCAL_OWNER


@dataclass(frozen=True)
class UserPaths:
    """Per-user storage locations (file backend)."""

    workspace_dir: Path
    notes_dir: Path
    screenshots_dir: Path
    data_dir: Path
    backups_dir: Path
    reminders_file: Path
    memories_file: Path
    action_log_file: Path
    chat_history_file: Path
    gemini_key_file: Path
    gemini_key_meta_file: Path


def user_paths(user: Optional[UserIdentity] = None) -> UserPaths:
    """Resolve storage paths for a user.

    Local owner -> the historical top-level settings paths.
    Any Google user -> ``<base>/users/<namespace>/...`` under each base dir,
    e.g. ``data/users/user_<hash>/reminders.json``.
    """
    u = resolve_user(user)
    if u.is_local_owner:
        return UserPaths(
            workspace_dir=settings.WORKSPACE_DIR,
            notes_dir=settings.NOTES_DIR,
            screenshots_dir=settings.SCREENSHOTS_DIR,
            data_dir=settings.DATA_DIR,
            backups_dir=settings.BACKUPS_DIR,
            reminders_file=settings.REMINDERS_FILE,
            memories_file=settings.MEMORIES_FILE,
            action_log_file=settings.ACTION_LOG_FILE,
            chat_history_file=settings.DATA_DIR / "chat_history.jsonl",
            gemini_key_file=settings.DATA_DIR / "gemini_key.enc",
            gemini_key_meta_file=settings.DATA_DIR / "gemini_key_meta.json",
        )
    ns = u.namespace
    data_dir = settings.DATA_DIR / "users" / ns
    return UserPaths(
        workspace_dir=settings.WORKSPACE_DIR / "users" / ns,
        notes_dir=settings.NOTES_DIR / "users" / ns,
        screenshots_dir=settings.SCREENSHOTS_DIR / "users" / ns,
        data_dir=data_dir,
        backups_dir=settings.BACKUPS_DIR / "users" / ns,
        reminders_file=data_dir / "reminders.json",
        memories_file=data_dir / "memories.json",
        action_log_file=settings.DATA_DIR / "users" / ns / "actions.jsonl",
        chat_history_file=data_dir / "chat_history.jsonl",
        gemini_key_file=data_dir / "gemini_key.enc",
        gemini_key_meta_file=data_dir / "gemini_key_meta.json",
    )
