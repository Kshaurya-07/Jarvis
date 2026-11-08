import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.logger import action_logger
from app.tools.base import ToolDefinition, ToolResult
from app.tools.workspace_tools import list_files, read_text_file
from app.tools.notes_tools import create_note, search_notes
from app.tools.app_control_tools import open_application
from app.tools.system_status_tools import get_battery_status, get_storage_status, get_memory_status
from app.tools.screenshot_tools import capture_screenshot, analyze_screenshot
from app.tools.reminders_tools import create_reminder, list_reminders, complete_reminder, delete_reminder
from app.tools.memory_tools import remember_item, forget_item, list_memories
from app.tools.search_tools import web_search
from app.tools.briefing_tools import get_daily_briefing


class ToolRegistry:
    """Central registry for managing agent tools, schema generation, and safe execution."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable[..., ToolResult],
    ) -> None:
        """Register a new tool with its definition and execution function."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        )

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> List[ToolDefinition]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_gemini_tool_declarations(self) -> List[Dict[str, Any]]:
        """Return function declarations formatted for the Gemini API."""
        return [tool.get_gemini_declaration() for tool in self._tools.values()]

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Safely execute a tool with server-side validation and audit logging.
        Never trusts model-generated arguments blindly.
        """
        start_time = time.perf_counter()

        if name not in self._tools:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Unknown tool '{name}'. Approved tools are: {list(self._tools.keys())}"
            action_logger.record_action(
                tool_name=name,
                status="failure",
                details=err_msg,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(success=False, error=err_msg)

        if not isinstance(arguments, dict):
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Invalid tool arguments: expected a JSON object/dict, got {type(arguments).__name__}."
            action_logger.record_action(
                tool_name=name,
                status="failure",
                details=err_msg,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(success=False, error=err_msg)

        tool_def = self._tools[name]

        # Server-side argument validation based on tool expectations
        try:
            validated_args = self._validate_args(name, arguments)
            result = tool_def.func(**validated_args)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            action_logger.record_action(
                tool_name=name,
                status="success" if result.success else "failure",
                details=f"success={result.success} | error={result.error or 'none'}",
                execution_time_ms=elapsed_ms,
            )
            return result
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Tool execution exception: {str(e)}"
            action_logger.record_action(
                tool_name=name,
                status="failure",
                details=err_msg,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(success=False, error=err_msg)

    def _validate_args(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize arguments per tool name."""
        if name == "list_files":
            subfolder = args.get("subfolder", "")
            return {"subfolder": str(subfolder) if not isinstance(subfolder, str) else subfolder}

        elif name == "read_text_file":
            filename = args.get("filename")
            if not filename or not isinstance(filename, str):
                raise ValueError("Argument 'filename' is required and must be a non-empty string.")
            return {"filename": filename.strip()}

        elif name == "create_note":
            title = args.get("title")
            if not title or not isinstance(title, str):
                raise ValueError("Argument 'title' is required and must be a non-empty string.")
            content = args.get("content", "")
            return {"title": title.strip(), "content": str(content) if not isinstance(content, str) else content}

        elif name == "search_notes":
            query = args.get("query")
            if not query or not isinstance(query, str):
                raise ValueError("Argument 'query' is required and must be a non-empty string.")
            return {"query": query.strip()}

        elif name == "open_application":
            app_name = args.get("app_name")
            if not app_name or not isinstance(app_name, str):
                raise ValueError("Argument 'app_name' is required and must be a non-empty string.")
            conf_id = args.get("confirmation_id")
            validated = {"app_name": app_name.strip()}
            if conf_id:
                validated["confirmation_id"] = str(conf_id).strip()
            return validated

        elif name == "get_battery_status":
            return {}

        elif name == "get_storage_status":
            drive = args.get("drive", "C:")
            return {"drive": str(drive).strip() if drive else "C:"}

        elif name == "get_memory_status":
            return {}

        elif name == "capture_screenshot":
            conf_id = args.get("confirmation_id")
            validated = {}
            if conf_id:
                validated["confirmation_id"] = str(conf_id).strip()
            return validated

        elif name == "analyze_screenshot":
            filename = args.get("screenshot_filename")
            if not filename or not isinstance(filename, str):
                raise ValueError("Argument 'screenshot_filename' is required.")
            prompt = args.get("prompt", "Describe what is shown in this screenshot.")
            conf_id = args.get("confirmation_id")
            validated = {
                "screenshot_filename": filename.strip(),
                "prompt": str(prompt).strip(),
            }
            if conf_id:
                validated["confirmation_id"] = str(conf_id).strip()
            return validated

        elif name == "create_reminder":
            title = args.get("title")
            if not title or not isinstance(title, str):
                raise ValueError("Argument 'title' is required and must be non-empty.")
            due_time = args.get("due_time")
            if not due_time or not isinstance(due_time, str):
                raise ValueError("Argument 'due_time' is required and must be non-empty.")
            notes = args.get("notes")
            return {
                "title": title.strip(),
                "due_time": due_time.strip(),
                "notes": str(notes).strip() if notes else None,
            }

        elif name == "list_reminders":
            inc_comp = args.get("include_completed", False)
            return {"include_completed": bool(inc_comp)}

        elif name == "complete_reminder":
            rem_id = args.get("reminder_id")
            if not rem_id or not isinstance(rem_id, str):
                raise ValueError("Argument 'reminder_id' is required.")
            return {"reminder_id": rem_id.strip()}

        elif name == "delete_reminder":
            rem_id = args.get("reminder_id")
            if not rem_id or not isinstance(rem_id, str):
                raise ValueError("Argument 'reminder_id' is required.")
            conf_id = args.get("confirmation_id")
            val = {"reminder_id": rem_id.strip()}
            if conf_id:
                val["confirmation_id"] = str(conf_id).strip()
            return val

        elif name == "remember_item":
            key = args.get("key")
            if not key or not isinstance(key, str):
                raise ValueError("Argument 'key' is required.")
            content = args.get("content")
            if not content or not isinstance(content, str):
                raise ValueError("Argument 'content' is required.")
            return {"key": key.strip(), "content": content.strip()}

        elif name == "forget_item":
            key = args.get("key")
            if not key or not isinstance(key, str):
                raise ValueError("Argument 'key' is required.")
            return {"key": key.strip()}

        elif name == "list_memories":
            return {}

        elif name == "web_search":
            query = args.get("query")
            if not query or not isinstance(query, str):
                raise ValueError("Argument 'query' is required and must be a non-empty string.")
            max_res = args.get("max_results", 5)
            try:
                max_res_int = int(max_res)
            except Exception:
                max_res_int = 5
            return {"query": query.strip(), "max_results": max_res_int}

        elif name == "get_daily_briefing":
            inc_web = args.get("include_web_summary", False)
            topics = args.get("web_topics")
            return {
                "include_web_summary": bool(inc_web),
                "web_topics": str(topics).strip() if topics else None,
            }

        return args


# Global registry instance
tool_registry = ToolRegistry()

# --- Register Phase 1 Tools ---

tool_registry.register(
    name="list_files",
    description="List files and subdirectories in the configured workspace folder.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "subfolder": {
                "type": "STRING",
                "description": "Optional relative subfolder path within the workspace to list. Leave empty for root.",
            }
        },
        "required": [],
    },
    func=list_files,
)

tool_registry.register(
    name="read_text_file",
    description="Read the text content of a file located within the configured workspace folder.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "filename": {
                "type": "STRING",
                "description": "The relative path of the text file to read inside the workspace.",
            }
        },
        "required": ["filename"],
    },
    func=read_text_file,
)

tool_registry.register(
    name="create_note",
    description="Save a new markdown note in the dedicated notes folder.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "title": {
                "type": "STRING",
                "description": "Title of the note (used for filename and heading).",
            },
            "content": {
                "type": "STRING",
                "description": "Full text or markdown content of the note.",
            },
        },
        "required": ["title", "content"],
    },
    func=create_note,
)

tool_registry.register(
    name="search_notes",
    description="Search through saved notes in the notes folder for a specific text query.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Text or keyword to search for across saved notes.",
            }
        },
        "required": ["query"],
    },
    func=search_notes,
)

# --- Register Phase 2 Tools ---

tool_registry.register(
    name="open_application",
    description=(
        "Open a pre-approved Windows application from the server allowlist (e.g. 'notepad', 'calculator', 'paint', 'explorer', 'cmd'). "
        "Requires explicit user confirmation before opening."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": "The identifier of the pre-approved app to launch (notepad, calculator, paint, explorer, cmd).",
            },
            "confirmation_id": {
                "type": "STRING",
                "description": "Optional confirmation token if the user has already approved this action.",
            },
        },
        "required": ["app_name"],
    },
    func=open_application,
)

tool_registry.register(
    name="get_battery_status",
    description="Retrieve current laptop battery charge percent, charging state, and power source.",
    parameters={
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    func=get_battery_status,
)

tool_registry.register(
    name="get_storage_status",
    description="Retrieve available and total disk storage capacity for a drive (e.g. 'C:').",
    parameters={
        "type": "OBJECT",
        "properties": {
            "drive": {
                "type": "STRING",
                "description": "Drive letter to query (defaults to 'C:').",
            }
        },
        "required": [],
    },
    func=get_storage_status,
)

tool_registry.register(
    name="get_memory_status",
    description="Retrieve current system RAM memory usage, free capacity, and total capacity.",
    parameters={
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    func=get_memory_status,
)

tool_registry.register(
    name="capture_screenshot",
    description=(
        "Capture a screenshot of the primary display and save it locally on the Windows host. "
        "Requires explicit user confirmation before capturing."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "confirmation_id": {
                "type": "STRING",
                "description": "Optional confirmation token if the user has already approved this action.",
            }
        },
        "required": [],
    },
    func=capture_screenshot,
)

tool_registry.register(
    name="analyze_screenshot",
    description=(
        "Send a locally saved screenshot to Gemini Multimodal vision for visual analysis. "
        "Requires explicit confirmation disclosing external transmission of the image."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "screenshot_filename": {
                "type": "STRING",
                "description": "The filename of the local screenshot in the screenshots directory.",
            },
            "prompt": {
                "type": "STRING",
                "description": "Question or analysis prompt for the vision model.",
            },
            "confirmation_id": {
                "type": "STRING",
                "description": "Optional confirmation token if the user has approved external image transmission.",
            },
        },
        "required": ["screenshot_filename"],
    },
    func=analyze_screenshot,
)

# --- Register Phase 4 Tools ---

tool_registry.register(
    name="create_reminder",
    description="Create and store a local reminder on the laptop with title and due time.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "title": {
                "type": "STRING",
                "description": "Subject or title of the reminder.",
            },
            "due_time": {
                "type": "STRING",
                "description": "When the reminder is due (e.g. 'Tomorrow at 10 AM', '2026-11-10 14:00').",
            },
            "notes": {
                "type": "STRING",
                "description": "Optional notes or additional details.",
            },
        },
        "required": ["title", "due_time"],
    },
    func=create_reminder,
)

tool_registry.register(
    name="list_reminders",
    description="List active or completed local reminders stored on the laptop.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "include_completed": {
                "type": "BOOLEAN",
                "description": "Whether to include already completed reminders (default false).",
            }
        },
        "required": [],
    },
    func=list_reminders,
)

tool_registry.register(
    name="complete_reminder",
    description="Mark a specific local reminder as completed using its reminder_id.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "reminder_id": {
                "type": "STRING",
                "description": "The unique ID of the reminder to mark complete (e.g. 'rem_1a2b3c4d').",
            }
        },
        "required": ["reminder_id"],
    },
    func=complete_reminder,
)

tool_registry.register(
    name="delete_reminder",
    description="Permanently delete a local reminder. Requires explicit confirmation before deletion.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "reminder_id": {
                "type": "STRING",
                "description": "The unique ID of the reminder to delete.",
            },
            "confirmation_id": {
                "type": "STRING",
                "description": "Optional confirmation token if already approved.",
            },
        },
        "required": ["reminder_id"],
    },
    func=delete_reminder,
)

tool_registry.register(
    name="remember_item",
    description="Explicitly save a piece of user-approved knowledge into persistent local memory.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "key": {
                "type": "STRING",
                "description": "A short key or category for this memory (e.g. 'preferred_language', 'user_goal').",
            },
            "content": {
                "type": "STRING",
                "description": "The content to remember.",
            },
        },
        "required": ["key", "content"],
    },
    func=remember_item,
)

tool_registry.register(
    name="forget_item",
    description="Delete a specific item from persistent local memory by its key.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "key": {
                "type": "STRING",
                "description": "The key of the memory to forget.",
            }
        },
        "required": ["key"],
    },
    func=forget_item,
)

tool_registry.register(
    name="list_memories",
    description="List all user-approved items currently stored in local persistent memory.",
    parameters={
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    func=list_memories,
)

# --- Register Phase 5 Tools ---

tool_registry.register(
    name="web_search",
    description=(
        "Search the web using an official search API (Tavily/Google/Brave) to retrieve a small number of factual results. "
        "Returns title, source, link, snippet, and publication date. Cites links in responses."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Specific search query (max 200 characters). Do not include personal data or credentials.",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Number of results to retrieve (1 to 10, default 5).",
            },
        },
        "required": ["query"],
    },
    func=web_search,
)

tool_registry.register(
    name="get_daily_briefing",
    description=(
        "Compile an on-demand daily briefing summarizing today's local reminders, recent notes/tasks, "
        "and optional current web updates. Never schedules background jobs or broadcasts."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "include_web_summary": {
                "type": "BOOLEAN",
                "description": "Whether to include an external web search summary (default false).",
            },
            "web_topics": {
                "type": "STRING",
                "description": "Specific non-personal topics to search for web overview (e.g. 'tech news', 'weather').",
            },
        },
        "required": [],
    },
    func=get_daily_briefing,
)
