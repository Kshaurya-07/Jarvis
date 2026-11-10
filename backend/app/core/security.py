from pathlib import Path
import re
from typing import Set

# Common text file extensions supported for read_text_file
ALLOWED_TEXT_EXTENSIONS: Set[str] = {
    ".txt", ".md", ".py", ".json", ".csv", ".log",
    ".yaml", ".yml", ".html", ".css", ".js", ".ts",
    ".sh", ".ini", ".cfg", ".toml", ".xml", ".rst",
    ".sql", ".env.example", ".gitignore"
}

class SecurityViolationError(Exception):
    """Raised when a path traversal, escaping directory, or security boundary violation is detected."""


class InvalidPathError(Exception):
    """Raised when a path is malformed or invalid."""


class FileSizeExceededError(Exception):
    """Raised when a requested file exceeds the configured maximum read size."""


class UnsupportedFileTypeError(Exception):
    """Raised when a non-text or binary file is requested."""


class UnsupportedPlatformError(Exception):
    """Raised when an OS-specific tool is called on an unsupported platform."""


def verify_windows_os(tool_name: str) -> None:
    """Verifies that the current operating system is Windows."""
    import sys
    if sys.platform != "win32":
        raise UnsupportedPlatformError(
            f"Tool '{tool_name}' is only supported on Windows operating systems (current: {sys.platform})."
        )


def resolve_safe_path(
    base_dir: Path,
    user_path: str,
    allow_root: bool = False,
    must_exist: bool = True
) -> Path:
    """
    Safely resolves a user-provided path relative to a base directory.
    
    Guarantees that:
    1. The path does not escape the base directory (no directory traversal `../` attacks).
    2. Null bytes and escape characters are rejected.
    3. The resolved canonical path is strictly a descendant of base_dir (or base_dir itself if allow_root=True).
    4. If must_exist=True, verifies that the target exists.
    """
    if not isinstance(user_path, str):
        raise InvalidPathError("Path must be a string.")

    user_path = user_path.strip()

    # Empty path handling
    if not user_path:
        if allow_root:
            return base_dir.resolve()
        raise InvalidPathError("Path cannot be empty.")

    # Null byte check
    if "\0" in user_path:
        raise SecurityViolationError("Path contains prohibited null bytes.")

    # Prohibit Windows Alternate Data Streams (ADS) and malformed colon syntax
    if ":" in user_path:
        # Only allow standard single drive letter at start (e.g. "C:\...") for absolute paths
        if not (len(user_path) >= 2 and user_path[1] == ":" and user_path[0].isalpha() and ":" not in user_path[2:]):
            raise SecurityViolationError("Path contains prohibited colon or alternate data stream indicator.")

    # Convert to pure path for component inspection
    path_obj = Path(user_path)

    # Base directory canonicalization
    base_canonical = base_dir.resolve()

    # Reject absolute Windows/POSIX drive roots if they try to target outside
    if path_obj.is_absolute():
        resolved = path_obj.resolve()
    else:
        resolved = (base_canonical / path_obj).resolve()

    # Critical boundary check: must be inside base_canonical (blocks traversal and symlink escapes)
    if not resolved.is_relative_to(base_canonical):
        raise SecurityViolationError(
            f"Access denied: Path '{user_path}' escapes the restricted boundary."
        )

    # Check root restriction
    if resolved == base_canonical and not allow_root:
        raise SecurityViolationError("Access denied: Root directory cannot be accessed as a file.")

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"File or directory not found: '{user_path}'")

    return resolved


def validate_text_file(path: Path, max_bytes: int) -> None:
    """
    Validates that a path points to an accessible text file within size limits.
    """
    if not path.is_file():
        raise InvalidPathError(f"Target '{path.name}' is not a regular file.")

    # Check file extension. Extension-less files are not exempt: a file
    # with no suffix is rejected unless its full name is explicitly
    # allowlisted (e.g. ".env.example", ".gitignore").
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_TEXT_EXTENSIONS and path.name not in ALLOWED_TEXT_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"File extension '{suffix or '(none)'}' is not supported. Supported text types: "
            f"{', '.join(sorted(ALLOWED_TEXT_EXTENSIONS))}"
        )

    # Check file size
    stat_result = path.stat()
    if stat_result.st_size > max_bytes:
        raise FileSizeExceededError(
            f"File '{path.name}' size ({stat_result.st_size} bytes) exceeds maximum "
            f"allowed size of {max_bytes} bytes."
        )


def sanitize_filename(name: str) -> str:
    """
    Sanitizes a user/model-provided title or filename for safe filesystem storage.
    Removes forbidden path characters and limits length.
    """
    if not name or not name.strip():
        raise InvalidPathError("Filename or note title cannot be empty.")

    cleaned = name.strip()
    # Remove directory traversal dot patterns
    cleaned = re.sub(r'\.{2,}', '_', cleaned)
    # Replace dangerous characters: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", cleaned)
    # Collapse consecutive underscores/spaces
    cleaned = re.sub(r'[\s_]+', '_', cleaned)
    # Strip leading/trailing dots, spaces, and underscores
    cleaned = cleaned.strip(". _")

    if not cleaned:
        raise InvalidPathError("Invalid filename after sanitization.")

    # Limit length to prevent OS filesystem errors
    return cleaned[:100]
