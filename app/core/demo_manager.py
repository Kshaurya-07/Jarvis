from typing import Any, Dict

from app import __version__
from app.core.config import settings
from app.core.logger import app_logger
from app.services.agent_service import agent_service
from app.tools.memory_tools import memory_storage
from app.tools.reminders_tools import reminders_storage


DEMO_STEPS = [
    {
        "step": 1,
        "title": "Start Local Backend",
        "description": "Backend binds strictly to localhost (http://127.0.0.1:8000). Visual indicator confirms connection.",
    },
    {
        "step": 2,
        "title": "Send Command from Companion",
        "description": "Send a text command from /mobile/ (e.g. 'What is the system status?' or 'Show my demo notes').",
    },
    {
        "step": 3,
        "title": "Open Local Fictional Demo Page",
        "description": "Navigate to http://127.0.0.1:8000/demo/ in Chrome. Contains fictional Europa space mission content.",
    },
    {
        "step": 4,
        "title": "Extract Page Text via Extension",
        "description": "Click the Jarvis Chrome extension icon on the demo tab and tap 'Read this page'. Shows extracted text and Gemini disclosure notice.",
    },
    {
        "step": 5,
        "title": "Grounded Study Response",
        "description": "Ask a question (e.g. 'What is the launch date of Deep Horizon?'). Jarvis answers grounded in the page without submitting answers.",
    },
    {
        "step": 6,
        "title": "Push-to-Talk Voice Input",
        "description": "Tap or hold the microphone button, speak, review and edit the transcript, then send.",
    },
    {
        "step": 7,
        "title": "Active Pause / Stop Control",
        "description": "Tap the visible 'Stop' button during execution to immediately cancel active in-flight requests.",
    },
    {
        "step": 8,
        "title": "Local Notes & Reminders",
        "description": "Seed mock demo data to inspect notes and reminders, then click 'Clear Demo Data' to reset in one step.",
    },
]


class DemoManager:
    """
    Manages Phase 10 end-to-end demo data seeding, status, and one-step cleanup.
    Keeps mock/demo data strictly isolated from real user data.
    """

    def get_status(self) -> Dict[str, Any]:
        """Return current status of the demo environment."""
        demo_notes = [f for f in settings.NOTES_DIR.glob("*.md") if f.name.startswith("demo_") or "[demo]" in f.name.lower()] if settings.NOTES_DIR.exists() else []
        demo_reminders = [r for r in reminders_storage.list_all(include_completed=True) if r.title.strip().upper().startswith("[DEMO]")]
        demo_memories = [m for m in memory_storage.list_all() if m.key.startswith("demo_")]

        return {
            "demo_version": "1.0",
            "app_version": __version__,
            "backend_connected": True,
            "gemini_configured": agent_service.is_configured(),
            "demo_page_url": "http://127.0.0.1:8000/demo/",
            "companion_url": "http://127.0.0.1:8000/mobile/",
            "active_demo_data": {
                "demo_notes_count": len(demo_notes),
                "demo_reminders_count": len(demo_reminders),
                "demo_memories_count": len(demo_memories),
            },
            "steps": DEMO_STEPS,
            "safety_guarantee": (
                "Demo mode uses fictional science data. Zero real accounts, zero real emails, "
                "zero live quizzes, and zero credit cards. Real user data is kept isolated."
            ),
        }

    def seed_demo_data(self) -> Dict[str, Any]:
        """
        Seed safe, fictional mock data for testing notes, reminders, and memory.
        Every seeded item is explicitly tagged with '[DEMO]'.
        """
        settings.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        demo_note_file = settings.NOTES_DIR / "demo_europa_mission_notes.md"
        demo_note_content = (
            "# [DEMO] Europa Deep Horizon Mission Brief\n\n"
            "- Target Launch: October 2032\n"
            "- Mission Destination: Europa (Jupiter II)\n"
            "- Scientific Goal: Characterize subsurface ocean habitability beneath ice shell\n"
            "- Payload Instruments: Deep-Ice Radar Sounder (DIRS), Sub-Plume Mass Spectrometer (SPMS)\n\n"
            "Notice: Fictional mission notes for Jarvis Phase 10 demo testing only."
        )
        demo_note_file.write_text(demo_note_content, encoding="utf-8")

        # Seed reminder
        rem_title = "[DEMO] Review Europa mission science objectives"
        existing = [r for r in reminders_storage.list_all(include_completed=True) if r.title == rem_title]
        if not existing:
            reminders_storage.add(
                title=rem_title,
                due_time="2032-10-01T14:00:00Z",
                notes="Fictional study reminder for Jarvis Phase 10 demo.",
            )

        # Seed memory
        memory_storage.put("demo_favorite_mission", "Europa Deep Horizon 2032")

        return {
            "status": "seeded",
            "message": "Fictional demo data successfully seeded.",
            "seeded_items": {
                "notes": 1,
                "reminders": 1,
                "memories": 1,
            },
            "note_file": str(demo_note_file.name),
        }

    def clear_demo_data(self) -> Dict[str, Any]:
        """
        One-step deletion of mock/demo data without touching real user data.
        Removes only files and records with 'demo_' prefix or '[DEMO]' tag.
        """
        deleted_notes = 0
        if settings.NOTES_DIR.exists():
            for f in list(settings.NOTES_DIR.glob("*.md")):
                if f.name.startswith("demo_") or "[demo]" in f.name.lower():
                    try:
                        f.unlink()
                        deleted_notes += 1
                    except Exception as e:
                        app_logger.warning("Failed to delete demo note '%s': %s", f.name, e)

        # Delete demo reminders
        deleted_reminders = 0
        all_reminders = reminders_storage.list_all(include_completed=True)
        for r in all_reminders:
            if r.title.strip().upper().startswith("[DEMO]"):
                if reminders_storage.delete(r.id):
                    deleted_reminders += 1

        # Delete demo memories
        deleted_memories = 0
        for m in memory_storage.list_all():
            if m.key.startswith("demo_"):
                if memory_storage.delete(m.key):
                    deleted_memories += 1

        return {
            "status": "cleared",
            "message": "Fictional demo data cleared successfully. Real user data remains untouched.",
            "deleted_items": {
                "notes": deleted_notes,
                "reminders": deleted_reminders,
                "memories": deleted_memories,
            },
        }


# Global instance
demo_manager = DemoManager()
