from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming user chat request payload."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="The user's text message or command for Jarvis.",
        examples=["List the files in my workspace folder.", "Create a note about my morning goals."]
    )


class ToolExecutionInfo(BaseModel):
    """Information regarding a tool invocation during the chat request."""
    tool_name: str
    arguments: Dict[str, Any]
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    """Response returned to the client from the chat endpoint."""
    reply: str
    tools_executed: List[ToolExecutionInfo] = Field(default_factory=list)
    success: bool
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """System health check status."""
    status: str
    version: str
    gemini_configured: bool
    workspace_directory: str
    notes_directory: str
    active_tools: List[str]


class ToolInfo(BaseModel):
    """Information about an active tool."""
    name: str
    description: str
    parameters: Dict[str, Any]
