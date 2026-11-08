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
    search_configured: bool = False
    search_provider: str = "tavily"
    platform: str
    workspace_directory: str
    notes_directory: str
    screenshots_directory: str
    reminders_count: int = 0
    memories_count: int = 0
    memory_enabled: bool = True
    active_tools: List[str]


class ToolInfo(BaseModel):
    """Information about an active tool."""
    name: str
    description: str
    parameters: Dict[str, Any]


class ConfirmationRequest(BaseModel):
    """Payload to confirm or deny a pending sensitive action."""
    confirmation_id: str = Field(..., description="Unique confirmation token.")
    approve: bool = Field(True, description="True to approve and execute, False to deny.")


class ConfirmationResponse(BaseModel):
    """Response after processing a confirmation request."""
    success: bool
    message: str
    tool_result: Optional[Dict[str, Any]] = None


class PendingActionInfo(BaseModel):
    """Information about an action currently awaiting user confirmation."""
    confirmation_id: str
    tool_name: str
    description: str
    arguments: Dict[str, Any]
    created_at: float
    expires_at: float


class PageReadRequest(BaseModel):
    """Request payload from the Jarvis Chrome extension when inspecting an active tab."""
    url: str = Field(..., max_length=2048, description="URL of the active tab.")
    title: str = Field(..., max_length=512, description="Title of the active tab.")
    page_text: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Extracted visible text from the active tab (max 50,000 characters).",
    )
    question: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional user question or practice quiz inquiry regarding page content.",
    )
    mode: str = Field(
        "summary",
        pattern=r"^(summary|quiz_help)$",
        description="Operation mode: 'summary' or 'quiz_help'.",
    )


class PageReadResponse(BaseModel):
    """Response returned to the Jarvis Chrome extension."""
    reply: str
    mode: str
    disclosure: str
    chars_processed: int
    success: bool
    error: Optional[str] = None


# --- Phase 4 Schemas ---

class ReminderCreateRequest(BaseModel):
    """Payload to create a new reminder."""
    title: str = Field(..., min_length=1, max_length=200, description="Title of the reminder.")
    due_time: str = Field(..., min_length=1, max_length=100, description="When the reminder is due.")
    notes: Optional[str] = Field(None, max_length=1000, description="Optional extra details.")


class ReminderResponse(BaseModel):
    """Reminder item representation."""
    id: str
    title: str
    due_time: str
    notes: Optional[str] = None
    completed: bool
    created_at: str
    completed_at: Optional[str] = None


class MemoryCreateRequest(BaseModel):
    """Payload to store or update user-approved memory."""
    key: str = Field(..., min_length=1, max_length=100, description="Memory key or category.")
    content: str = Field(..., min_length=1, max_length=2000, description="Information to remember.")


class MemoryResponse(BaseModel):
    """Memory item representation."""
    key: str
    content: str
    created_at: str
    updated_at: str


class MemoryStatusResponse(BaseModel):
    """Memory system status."""
    enabled: bool
    count: int


class MemoryToggleRequest(BaseModel):
    """Payload to toggle memory feature state."""
    enabled: bool


# --- Phase 5 Schemas ---

class DailyBriefingResponse(BaseModel):
    """Structured response for on-demand daily briefing."""
    briefing_type: str
    generated_at: str
    local_reminders: Dict[str, Any]
    local_notes: Dict[str, Any]
    web_overview: Optional[Dict[str, Any]] = None
    attribution: str
    formatting_instructions: str
