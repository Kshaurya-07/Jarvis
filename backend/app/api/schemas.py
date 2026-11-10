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
    reminders_count: int = 0
    memories_count: int = 0
    memory_enabled: bool = True
    google_connected: bool = False
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


# --- Phase 6 Schemas (Google OAuth, Gmail & Calendar) ---

class GoogleAuthUrlResponse(BaseModel):
    """Response containing Google OAuth authorization URL and state token."""
    auth_url: str
    state: str
    scopes: List[str]


class GoogleAuthStatusResponse(BaseModel):
    """Google OAuth connection status and storage backend metadata."""
    connected: bool
    account_email: Optional[str] = None
    scopes: List[str]
    storage_backend: str
    connected_at: Optional[str] = None
    read_only: bool = True


class GoogleDisconnectResponse(BaseModel):
    """Response from disconnecting and revoking Google OAuth account."""
    status: str
    message: str
    revoked_remotely: bool
    revocation_guide: str = (
        "Tokens have been deleted from local storage. To review or manually revoke Jarvis "
        "permissions from your Google Account at any time, visit: https://myaccount.google.com/permissions"
    )


class GmailListResponse(BaseModel):
    """Response from listing recent Gmail messages."""
    count: int
    messages: List[Dict[str, Any]]
    filter_query: Optional[str] = None
    read_only: bool = True


class GmailSummarizeRequest(BaseModel):
    """Request payload to summarize Gmail messages."""
    message_ids: Optional[List[str]] = None
    max_results: int = 3
    query: Optional[str] = None
    custom_instructions: Optional[str] = None


class GmailSummarizeResponse(BaseModel):
    """Response containing Gemini summary of email messages."""
    count: int
    summary: str
    analyzed_messages: Optional[List[Dict[str, Any]]] = None
    disclosure: str
    read_only: bool = True


class CalendarListResponse(BaseModel):
    """Response from listing Google Calendar events."""
    count: int
    events: List[Dict[str, Any]]
    time_min: str
    time_max: str
    read_only: bool = True


class CalendarSummarizeRequest(BaseModel):
    """Request payload to summarize calendar events for a date range."""
    time_min: Optional[str] = None
    time_max: Optional[str] = None
    calendar_id: str = "primary"


class CalendarSummarizeResponse(BaseModel):
    """Response containing Gemini summary of calendar events."""
    count: int
    summary: str
    disclosure: str
    time_min: Optional[str] = None
    time_max: Optional[str] = None
    read_only: bool = True


# --- Phase 8 Schemas (Limited Browser Automation) ---

class ApprovedDomainsResponse(BaseModel):
    """List of user-approved domains for browser automation."""
    approved_domains: List[str]


class ApproveDomainRequest(BaseModel):
    """Request payload to add a domain to the user-approved list."""
    domain: str = Field(..., min_length=3, max_length=150, description="Domain to approve, e.g. 'wikipedia.org'.")


class BrowserPlanActionRequest(BaseModel):
    """Payload to validate and plan a low-risk browser action."""
    action_type: str = Field(..., description="'navigate', 'read_page', or 'fill_field'")
    approved_domain: str = Field(..., description="The user-approved domain.")
    url: Optional[str] = Field(None, description="Target URL for navigation or reading.")
    selector: Optional[str] = Field(None, description="CSS selector for target field.")
    value: Optional[str] = Field(None, description="Non-sensitive value to fill.")
    field_description: Optional[str] = Field(None, description="Human description of target field.")


class BrowserPlanActionResponse(BaseModel):
    """Response from planning a browser action with safety validation & confirmation."""
    allowed: bool
    action_type: str
    approved_domain: str
    requires_confirmation: bool
    confirmation_id: Optional[str] = None
    description: Optional[str] = None
    warning: Optional[str] = None
    error: Optional[str] = None


# --- Phase 9 Schemas (User Data Controls, Backup & Recovery) ---

class DataLocationsResponse(BaseModel):
    """Information on local filesystem data storage locations."""
    locations: Dict[str, Any]
    oauth_storage: Dict[str, Any]
    disclosure: str


class DataExportResponse(BaseModel):
    """User data export containing notes, reminders, and memories."""
    export_format_version: str
    exported_at: str
    app_version: str
    data: Dict[str, Any]
    summary: Dict[str, int]
    privacy_notice: str


class DataClearRequest(BaseModel):
    """Payload to confirm clearing all local user data."""
    confirm: bool = Field(..., description="Must be true to authorize deletion.")
    confirmation_text: str = Field(..., description="Must exactly match 'DELETE ALL DATA'.")


class DataClearResponse(BaseModel):
    """Response confirming deletion of user data."""
    status: str
    message: str
    deleted_items: Dict[str, int]
    timestamp: str


class BackupCreateRequest(BaseModel):
    """Optional payload to create a named local backup."""
    backup_name: Optional[str] = Field(None, max_length=50, description="Optional custom name for backup file.")


class BackupCreateResponse(BaseModel):
    """Response confirming backup creation with integrity checksum."""
    status: str
    backup_filename: str
    backup_path: str
    created_at: str
    checksum: str
    summary: Dict[str, int]


class BackupRestoreRequest(BaseModel):
    """Payload to restore data from a validated local backup."""
    backup_filename: str = Field(..., description="Name of the backup file in backups/ to restore.")
    confirm_overwrite: bool = Field(False, description="Must be true to authorize overwriting existing local data.")


class BackupRestoreResponse(BaseModel):
    """Response confirming restoration of data from backup."""
    status: str
    message: str
    restored_items: Dict[str, int]
    timestamp: str


class BackupListResponse(BaseModel):
    """List of all local backup files with verification status."""
    count: int
    backups: List[Dict[str, Any]]


# --- Phase 10 Schemas (End-to-End Demo Mode) ---

class DemoStepInfo(BaseModel):
    step: int
    title: str
    description: str


class DemoStatusResponse(BaseModel):
    """Status and instructions for the Phase 10 local end-to-end demo."""
    demo_version: str
    app_version: str
    backend_connected: bool
    gemini_configured: bool
    companion_url: str
    active_demo_data: Dict[str, int]
    steps: List[DemoStepInfo]
    safety_guarantee: str


class DemoActionResponse(BaseModel):
    """Response from seeding or clearing mock demo data."""
    status: str
    message: str
    seeded_items: Optional[Dict[str, int]] = None
    deleted_items: Optional[Dict[str, int]] = None
    note_file: Optional[str] = None


# --- Phase 11 Schemas (Tailscale Phone-to-Laptop Control) ---

class PairingGenerateResponse(BaseModel):
    """Response containing newly generated one-time pairing code for remote device pairing."""
    pairing_code: str
    expires_in_seconds: int
    instructions: str


class PairingExchangeRequest(BaseModel):
    """Request payload from remote client exchanging one-time pairing code for in-memory session token."""
    pairing_code: str = Field(..., min_length=4, max_length=16)


class PairingExchangeResponse(BaseModel):
    """Response containing in-memory session token for authenticated remote calls."""
    session_token: str
    expires_in_seconds: int
    token_type: str = "Bearer"


class SessionStatusResponse(BaseModel):
    """Response verifying whether the currently held session token is active."""
    valid: bool
    expires_in_seconds: Optional[int] = None
    detail: Optional[str] = None


class SessionRevokeResponse(BaseModel):
    """Response from revoking an active session token upon user disconnect."""
    revoked: bool
    message: str


class RemoteStopResponse(BaseModel):
    """Response from halting active tasks via remote stop control."""
    stopped: bool
    message: str







# --- Phase 12 Schemas (Google sign-in, BYOK key) ---

class ApiKeyRequest(BaseModel):
    """Payload carrying the user's own Gemini API key (BYOK)."""
    api_key: str = Field(..., min_length=10, max_length=200, description="The user's own Gemini API key from Google AI Studio.")


class KeyStatusResponse(BaseModel):
    """Public status of the user's saved Gemini key. Never contains the key."""
    has_key: bool
    hint: Optional[str] = None
    created_at: Optional[str] = None
    valid: Optional[bool] = None
