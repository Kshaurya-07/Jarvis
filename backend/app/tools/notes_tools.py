"""Notes tools — per-user via the active UserStore (Phase 12).

In production (DATABASE_URL set) notes live in Postgres; locally they
live in the user's namespaced notes directory. Either way a user can only
create/search their own notes.
"""
import datetime
from typing import Any, Dict, List, Optional

from app.core.security import (
    SecurityViolationError,
    InvalidPathError,
)
from app.core.store import get_user_store
from app.core.user_context import UserIdentity, get_current_user, resolve_user
from app.tools.base import ToolResult


def create_note(title: str, content: str, user: Optional[UserIdentity] = None) -> ToolResult:
    """
    Save a note in the user's dedicated notes folder (or Postgres row).

    Args:
        title: Title of the note (used for filename and header).
        content: Text content of the note.
        user: Signed-in user; defaults to the current request's user.
    """
    u = resolve_user(user or get_current_user())
    try:
        if not isinstance(title, str) or not title.strip():
            return ToolResult(success=False, error="Note title must be a non-empty string.")
        if not isinstance(content, str):
            content = str(content)
        result = get_user_store().create_note(u, title, content)
        return ToolResult(success=True, output=result)
    except (SecurityViolationError, InvalidPathError) as e:
        return ToolResult(success=False, error=f"Security/Path error: {str(e)}")
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to create note: {str(e)}")


def search_notes(query: str, user: Optional[UserIdentity] = None) -> ToolResult:
    """
    Search the user's saved notes by text.

    Args:
        query: Text search term to search for across notes.
        user: Signed-in user; defaults to the current request's user.
    """
    u = resolve_user(user or get_current_user())
    try:
        if not isinstance(query, str) or not query.strip():
            return ToolResult(success=False, error="Search query must be a non-empty string.")
        matches = get_user_store().search_notes(u, query)
        return ToolResult(
            success=True,
            output={
                "query": query,
                "files_matched": len(matches),
                "matches": matches,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to search notes: {str(e)}")
