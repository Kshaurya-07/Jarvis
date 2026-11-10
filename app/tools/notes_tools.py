import datetime
from typing import Any, Dict, List

from app.core.config import settings
from app.core.security import (
    resolve_safe_path,
    sanitize_filename,
    SecurityViolationError,
    InvalidPathError,
)
from app.tools.base import ToolResult


def create_note(title: str, content: str) -> ToolResult:
    """
    Save a note in the dedicated notes folder.
    
    Args:
        title: Title of the note (used for filename and header).
        content: Text content of the note.
    """
    try:
        if not isinstance(title, str) or not title.strip():
            return ToolResult(
                success=False,
                error="Note title must be a non-empty string.",
            )
        if not isinstance(content, str):
            content = str(content)

        clean_title = sanitize_filename(title)
        filename = f"{clean_title}.md"

        notes_dir = settings.NOTES_DIR
        target_path = resolve_safe_path(
            base_dir=notes_dir,
            user_path=filename,
            allow_root=False,
            must_exist=False,
        )

        # Avoid accidental overwrite if exact file already exists: append timestamp suffix if different
        if target_path.exists():
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{clean_title}_{timestamp_str}.md"
            target_path = resolve_safe_path(
                base_dir=notes_dir,
                user_path=filename,
                allow_root=False,
                must_exist=False,
            )

        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted_content = f"# {title.strip()}\n*Created: {now_iso}*\n\n{content}\n"

        target_path.write_text(formatted_content, encoding="utf-8")

        return ToolResult(
            success=True,
            output={
                "title": title.strip(),
                "filename": target_path.name,
                "relative_path": str(target_path.relative_to(notes_dir)).replace("\\", "/"),
                "bytes_written": len(formatted_content.encode("utf-8")),
            },
        )

    except (SecurityViolationError, InvalidPathError) as e:
        return ToolResult(success=False, error=f"Security/Path error: {str(e)}")
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to create note: {str(e)}")


def search_notes(query: str) -> ToolResult:
    """
    Search saved notes by text in the dedicated notes folder.
    
    Args:
        query: Text search term to search for across notes.
    """
    try:
        if not isinstance(query, str) or not query.strip():
            return ToolResult(
                success=False,
                error="Search query must be a non-empty string.",
            )

        notes_dir = settings.NOTES_DIR
        if not notes_dir.exists():
            return ToolResult(
                success=True,
                output={
                    "query": query,
                    "matches_count": 0,
                    "matches": [],
                },
            )

        search_term = query.strip().lower()
        matches: List[Dict[str, Any]] = []

        # Scan text and markdown files in notes_dir
        for file_path in sorted(notes_dir.glob("*.md")) + sorted(notes_dir.glob("*.txt")):
            if not file_path.is_file():
                continue

            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = text.splitlines()
            matching_lines = []
            for line_idx, line in enumerate(lines, start=1):
                if search_term in line.lower():
                    matching_lines.append({
                        "line_number": line_idx,
                        "text": line.strip()[:200],  # Limit snippet length
                    })

            if matching_lines:
                matches.append({
                    "filename": file_path.name,
                    "relative_path": str(file_path.relative_to(notes_dir)).replace("\\", "/"),
                    "total_matches_in_file": len(matching_lines),
                    "snippets": matching_lines[:5],  # Top 5 matching snippets per file
                })

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
