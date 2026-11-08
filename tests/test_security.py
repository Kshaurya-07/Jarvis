from pathlib import Path
import pytest

from app.core.security import (
    resolve_safe_path,
    validate_text_file,
    sanitize_filename,
    SecurityViolationError,
    InvalidPathError,
    FileSizeExceededError,
    UnsupportedFileTypeError,
)


def test_resolve_safe_path_valid(tmp_path: Path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    file = sub / "test.txt"
    file.write_text("hello", encoding="utf-8")

    resolved = resolve_safe_path(tmp_path, "subdir/test.txt")
    assert resolved == file.resolve()


def test_resolve_safe_path_traversal_attack(tmp_path: Path):
    with pytest.raises(SecurityViolationError):
        resolve_safe_path(tmp_path, "../outside.txt", must_exist=False)

    with pytest.raises(SecurityViolationError):
        resolve_safe_path(tmp_path, "../../etc/passwd", must_exist=False)

    with pytest.raises(SecurityViolationError):
        resolve_safe_path(tmp_path, "subdir/../../outside.txt", must_exist=False)


def test_resolve_safe_path_absolute_drive_escape(tmp_path: Path):
    with pytest.raises(SecurityViolationError):
        resolve_safe_path(tmp_path, "C:/Windows/System32/cmd.exe", must_exist=False)


def test_resolve_safe_path_null_byte(tmp_path: Path):
    with pytest.raises(SecurityViolationError):
        resolve_safe_path(tmp_path, "file.txt\0.exe", must_exist=False)


def test_resolve_safe_path_empty_handling(tmp_path: Path):
    with pytest.raises(InvalidPathError):
        resolve_safe_path(tmp_path, "", allow_root=False)

    root = resolve_safe_path(tmp_path, "", allow_root=True)
    assert root == tmp_path.resolve()


def test_validate_text_file_success(tmp_path: Path):
    txt_file = tmp_path / "notes.md"
    txt_file.write_text("# Hello World", encoding="utf-8")
    validate_text_file(txt_file, max_bytes=1000)


def test_validate_text_file_unsupported_extension(tmp_path: Path):
    binary_file = tmp_path / "program.exe"
    binary_file.write_bytes(b"\x00\x01\x02\x03")

    with pytest.raises(UnsupportedFileTypeError) as exc:
        validate_text_file(binary_file, max_bytes=1000)
    assert ".exe" in str(exc.value)


def test_validate_text_file_size_exceeded(tmp_path: Path):
    large_file = tmp_path / "large.txt"
    large_file.write_text("A" * 2000, encoding="utf-8")

    with pytest.raises(FileSizeExceededError):
        validate_text_file(large_file, max_bytes=1000)


def test_sanitize_filename():
    assert sanitize_filename("My Note: Part 1?*") == "My_Note_Part_1"
    assert sanitize_filename("test/../../danger") == "test_danger"
    assert sanitize_filename("...hello...") == "hello"

    with pytest.raises(InvalidPathError):
        sanitize_filename("")

    with pytest.raises(InvalidPathError):
        sanitize_filename("   ...   ")
