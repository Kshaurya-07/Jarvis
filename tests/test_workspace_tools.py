from pathlib import Path
import pytest

from app.core.config import settings
from app.tools.workspace_tools import list_files, read_text_file


def test_list_files_empty():
    result = list_files()
    assert result.success is True
    assert result.output["count"] == 0
    assert result.output["items"] == []


def test_list_files_with_contents():
    ws = settings.WORKSPACE_DIR
    (ws / "file1.txt").write_text("Hello", encoding="utf-8")
    (ws / "file2.py").write_text("print('test')", encoding="utf-8")
    sub = ws / "subfolder"
    sub.mkdir()
    (sub / "nested.md").write_text("# Nested", encoding="utf-8")

    result = list_files()
    assert result.success is True
    assert result.output["count"] == 3
    names = [item["name"] for item in result.output["items"]]
    assert "file1.txt" in names
    assert "file2.py" in names
    assert "subfolder" in names

    # Subfolder listing
    sub_res = list_files(subfolder="subfolder")
    assert sub_res.success is True
    assert sub_res.output["count"] == 1
    assert sub_res.output["items"][0]["name"] == "nested.md"


def test_list_files_traversal_blocked():
    result = list_files(subfolder="../../")
    assert result.success is False
    assert "escapes the restricted boundary" in result.error


def test_read_text_file_success():
    ws = settings.WORKSPACE_DIR
    test_file = ws / "sample.py"
    test_file.write_text("def hello(): return 42\n", encoding="utf-8")

    result = read_text_file(filename="sample.py")
    assert result.success is True
    assert result.output["filename"] == "sample.py"
    assert "def hello(): return 42" in result.output["content"]


def test_read_text_file_missing():
    result = read_text_file(filename="does_not_exist.txt")
    assert result.success is False
    assert "not found" in result.error.lower()


def test_read_text_file_traversal_blocked():
    result = read_text_file(filename="../secret.txt")
    assert result.success is False
    assert "escapes the restricted boundary" in result.error


def test_read_text_file_unsupported_binary():
    ws = settings.WORKSPACE_DIR
    binary = ws / "binary.bin"
    binary.write_bytes(b"\x00\xFF\xFE\x00")

    result = read_text_file(filename="binary.bin")
    assert result.success is False
    assert "not supported" in result.error


def test_read_text_file_size_exceeded():
    ws = settings.WORKSPACE_DIR
    big_file = ws / "huge.txt"
    # Settings in conftest limit to 50KB
    big_file.write_text("X" * (1024 * 60), encoding="utf-8")

    result = read_text_file(filename="huge.txt")
    assert result.success is False
    assert "exceeds maximum allowed size" in result.error
