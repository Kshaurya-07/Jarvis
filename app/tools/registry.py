import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.logger import action_logger
from app.tools.base import ToolDefinition, ToolResult
from app.tools.workspace_tools import list_files, read_text_file
from app.tools.notes_tools import create_note, search_notes


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
            if not isinstance(subfolder, str):
                subfolder = str(subfolder)
            return {"subfolder": subfolder}

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
            if not isinstance(content, str):
                content = str(content)
            return {"title": title.strip(), "content": content}

        elif name == "search_notes":
            query = args.get("query")
            if not query or not isinstance(query, str):
                raise ValueError("Argument 'query' is required and must be a non-empty string.")
            return {"query": query.strip()}

        return args


# Global registry instance
tool_registry = ToolRegistry()

# Register Phase 1 Tools
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
