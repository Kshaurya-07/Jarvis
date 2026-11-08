from pathlib import Path
import pytest

from app.core.config import settings
from app.tools.notes_tools import create_note, search_notes


def test_create_note_success():
    result = create_note(title="Weekly Plan", content="Complete Jarvis Phase 1 backend.")
    assert result.success is True
    assert result.output["title"] == "Weekly Plan"
    assert result.output["filename"] == "Weekly_Plan.md"

    saved_file = settings.NOTES_DIR / "Weekly_Plan.md"
    assert saved_file.exists()
    content = saved_file.read_text(encoding="utf-8")
    assert "# Weekly Plan" in content
    assert "Complete Jarvis Phase 1 backend." in content


def test_create_note_sanitizes_title():
    result = create_note(
        title="Project: Ideas / v1.0?",
        content="Testing character sanitization.",
    )
    assert result.success is True
    assert result.output["filename"] == "Project_Ideas_v1.0.md"
    assert (settings.NOTES_DIR / "Project_Ideas_v1.0.md").exists()


def test_create_note_empty_title_rejected():
    result = create_note(title="   ", content="No title note")
    assert result.success is False
    assert "non-empty string" in result.error


def test_search_notes_finds_matches():
    create_note(title="Project Alpha", content="Architecture meeting regarding FastAPI microservices.")
    create_note(title="Shopping List", content="Buy coffee, apples, and milk.")
    create_note(title="Project Beta", content="Docker containers and FastAPI deployment.")

    search_res = search_notes(query="FastAPI")
    assert search_res.success is True
    assert search_res.output["files_matched"] == 2
    matched_filenames = [m["filename"] for m in search_res.output["matches"]]
    assert "Project_Alpha.md" in matched_filenames
    assert "Project_Beta.md" in matched_filenames


def test_search_notes_case_insensitive():
    create_note(title="Secret Recipe", content="Add three tablespoons of Sugar.")

    search_res = search_notes(query="sugar")
    assert search_res.success is True
    assert search_res.output["files_matched"] == 1
    assert search_res.output["matches"][0]["filename"] == "Secret_Recipe.md"


def test_search_notes_no_match():
    create_note(title="Empty Notes", content="Just some text here.")

    search_res = search_notes(query="nonexistent_keyword_12345")
    assert search_res.success is True
    assert search_res.output["files_matched"] == 0
    assert search_res.output["matches"] == []
