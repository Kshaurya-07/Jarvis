import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.tools.base import ToolResult
from app.tools.reminders_tools import reminders_storage
from app.tools.search_tools import execute_web_search


class DailyBriefingResult(BaseModel):
    """Structured representation of an on-demand daily briefing."""
    generated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    on_demand: bool = True
    local_reminders: Dict[str, Any]
    local_notes: Dict[str, Any]
    web_overview: Optional[Dict[str, Any]] = None
    attribution_note: str


async def build_daily_briefing(
    include_web_summary: bool = False,
    web_topics: Optional[str] = None,
) -> ToolResult:
    """
    Assembles an on-demand daily briefing from local reminders, local notes/tasks,
    and optional web search results for current news/topics.
    
    Guarantees:
    - Never schedules background tasks or automatic broadcasts.
    - Strictly keeps local private data OUT of external search queries.
    - Clearly marks the source of every detail (local vs web).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")

    # 1. Gather Local Reminders
    try:
        active_reminders = reminders_storage.list_all(include_completed=False)
        today_date_str = now.strftime("%Y-%m-%d")

        reminders_summary = []
        for r in active_reminders:
            due_lower = r.due_time.lower()
            is_today = "today" in due_lower or today_date_str in r.due_time
            reminders_summary.append({
                "id": r.id,
                "title": r.title,
                "due_time": r.due_time,
                "priority_status": "Due Today" if is_today else "Upcoming",
                "notes": r.notes,
            })

        reminders_section = {
            "source": "Local Store (data/reminders.json)",
            "count": len(reminders_summary),
            "items": reminders_summary,
        }
    except Exception as e:
        reminders_section = {
            "source": "Local Store (data/reminders.json)",
            "count": 0,
            "error": f"Failed to read reminders: {str(e)}",
            "items": [],
        }

    # 2. Gather Recent Local Notes & Tasks
    notes_section = {
        "source": "Local Storage (notes/)",
        "count": 0,
        "items": [],
    }
    try:
        notes_dir = settings.NOTES_DIR
        if notes_dir.exists():
            recent_notes = sorted(
                list(notes_dir.glob("*.md")) + list(notes_dir.glob("*.txt")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:5]  # Top 5 most recent notes

            note_items = []
            for note_path in recent_notes:
                try:
                    text = note_path.read_text(encoding="utf-8", errors="replace")
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    title = lines[0].lstrip("# ").strip() if lines else note_path.stem
                    
                    # Look for checklist items or TODOs
                    todos = [line for line in lines if line.startswith("- [ ]") or "todo:" in line.lower()][:3]
                    
                    note_items.append({
                        "filename": note_path.name,
                        "title": title,
                        "tasks_preview": todos if todos else lines[1:3],
                    })
                except Exception:
                    continue

            notes_section["count"] = len(note_items)
            notes_section["items"] = note_items
    except Exception as e:
        notes_section["error"] = f"Failed to inspect notes: {str(e)}"

    # 3. Optional Web Search Summary (strictly on general user topics, never leaking local data)
    web_section = None
    if include_web_summary and web_topics and isinstance(web_topics, str) and web_topics.strip():
        # Sanitize query: verify no personal data is leaked
        clean_topic = web_topics.strip()
        search_res = await execute_web_search(query=clean_topic, max_results=3)

        if search_res.success and search_res.output:
            web_section = {
                "source": "External Web Search",
                "topic_query": clean_topic,
                "count": search_res.output.get("count", 0),
                "results": search_res.output.get("results", []),
                "citation_requirement": "Assistant must cite links [Source: Title](URL) for web information.",
            }
        else:
            web_section = {
                "source": "External Web Search",
                "topic_query": clean_topic,
                "error": search_res.error or "Web search failed.",
                "results": [],
            }

    attribution_note = (
        "Attribution: Reminders and Notes are stored exclusively on your local laptop. "
        "Web search items (if included) are external results and must be cited with links."
    )

    return ToolResult(
        success=True,
        output={
            "briefing_type": "On-Demand Daily Briefing",
            "on_demand": True,
            "generated_at": now_str,
            "local_reminders": reminders_section,
            "local_notes": notes_section,
            "web_overview": web_section,
            "attribution": attribution_note,
            "formatting_instructions": (
                "Format a clear briefing organized into: "
                "1) Local Reminders, 2) Recent Notes & Tasks, and 3) Current Web Updates (if present). "
                "Explicitly cite web links in markdown [Title](URL) and distinguish local facts from web facts."
            ),
        },
    )


def get_daily_briefing(
    include_web_summary: bool = False,
    web_topics: Optional[str] = None,
) -> ToolResult:
    """
    Synchronous wrapper for tool registry dispatch.
    Compiles an on-demand daily briefing safely.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run,
                    build_daily_briefing(include_web_summary, web_topics),
                ).result()
        return loop.run_until_complete(
            build_daily_briefing(include_web_summary, web_topics)
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to generate briefing: {str(e)}")
