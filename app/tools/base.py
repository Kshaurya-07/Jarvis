from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Standardized result returned by any tool execution."""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


class ToolDefinition:
    """Holds a tool function, metadata, and JSON schema for Gemini function calling."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable[..., ToolResult],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def get_gemini_declaration(self) -> Dict[str, Any]:
        """Returns the dictionary representation for Gemini function declaration."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
