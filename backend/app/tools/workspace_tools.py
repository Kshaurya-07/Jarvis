from typing import Any, Dict, List

from app.core.config import settings
from app.core.security import (
    resolve_safe_path,
    validate_text_file,
    SecurityViolationError,
    InvalidPathError,
    FileSizeExceededError,
    UnsupportedFileTypeError,
)
from app.tools.base import ToolResult


def list_files(subfolder: str = "", user=None) -> ToolResult:
    """
    List files and directories inside the explicitly configured workspace folder.
    
    Args:
        subfolder: Optional subfolder path within the workspace to list.
    """
    try:
        if not isinstance(subfolder, str):
            subfolder = str(subfolder)

        from app.core.user_context import get_current_user, resolve_user, user_paths

        workspace_dir = user_paths(resolve_user(user or get_current_user())).workspace_dir
        target_dir = resolve_safe_path(
            base_dir=workspace_dir,
            user_path=subfolder,
            allow_root=True,
            must_exist=True,
        )

        if not target_dir.is_dir():
            return ToolResult(
                success=False,
                error=f"Target path '{subfolder}' is not a directory.",
            )

        entries: List[Dict[str, Any]] = []
        for item in sorted(target_dir.iterdir()):
            is_file = item.is_file()
            rel_path = str(item.relative_to(workspace_dir)).replace("\\", "/")
            item_info: Dict[str, Any] = {
                "name": item.name,
                "relative_path": rel_path,
                "type": "file" if is_file else "directory",
            }
            if is_file:
                item_info["size_bytes"] = item.stat().st_size
            entries.append(item_info)

        return ToolResult(
            success=True,
            output={
                "folder": str(target_dir.relative_to(workspace_dir)).replace("\\", "/") if target_dir != workspace_dir else "/",
                "count": len(entries),
                "items": entries,
            },
        )

    except (SecurityViolationError, InvalidPathError) as e:
        return ToolResult(success=False, error=f"Path validation failed: {str(e)}")
    except FileNotFoundError as e:
        return ToolResult(success=False, error=f"Path not found: {str(e)}")
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to list files: {str(e)}")


def read_text_file(filename: str, user=None) -> ToolResult:
    """
    Read the contents of a text file inside the explicitly configured workspace folder.
    
    Args:
        filename: Relative path of the file to read within the workspace folder.
    """
    try:
        if not isinstance(filename, str) or not filename.strip():
            return ToolResult(
                success=False,
                error="Filename parameter is required and must be a non-empty string.",
            )

        from app.core.user_context import get_current_user, resolve_user, user_paths

        workspace_dir = user_paths(resolve_user(user or get_current_user())).workspace_dir
        safe_path = resolve_safe_path(
            base_dir=workspace_dir,
            user_path=filename,
            allow_root=False,
            must_exist=True,
        )

        # Validate file type and size
        validate_text_file(safe_path, max_bytes=settings.MAX_FILE_READ_BYTES)

        # Read file with UTF-8 decoding and error replacement
        try:
            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                error=f"File '{filename}' contains non-UTF-8 characters or binary data and cannot be read as text.",
            )

        rel_path = str(safe_path.relative_to(workspace_dir)).replace("\\", "/")
        return ToolResult(
            success=True,
            output={
                "filename": safe_path.name,
                "relative_path": rel_path,
                "size_bytes": len(content.encode("utf-8")),
                "content": content,
            },
        )

    except (SecurityViolationError, InvalidPathError) as e:
        return ToolResult(success=False, error=f"Security/Path error: {str(e)}")
    except FileNotFoundError as e:
        return ToolResult(success=False, error=f"File not found: {str(e)}")
    except (UnsupportedFileTypeError, FileSizeExceededError) as e:
        return ToolResult(success=False, error=f"File validation error: {str(e)}")
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to read file: {str(e)}")
