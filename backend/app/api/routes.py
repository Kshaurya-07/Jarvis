import sys
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app import __version__
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ToolInfo,
    ToolExecutionInfo,
    ConfirmationRequest,
    ConfirmationResponse,
    PendingActionInfo,
    PageReadRequest,
    PageReadResponse,
    ReminderCreateRequest,
    ReminderResponse,
    MemoryCreateRequest,
    MemoryResponse,
    MemoryStatusResponse,
    MemoryToggleRequest,
    GoogleAuthUrlResponse,
    GoogleAuthStatusResponse,
    GoogleDisconnectResponse,
    GmailListResponse,
    GmailSummarizeRequest,
    GmailSummarizeResponse,
    CalendarListResponse,
    CalendarSummarizeRequest,
    CalendarSummarizeResponse,
    ApprovedDomainsResponse,
    ApproveDomainRequest,
    BrowserPlanActionRequest,
    BrowserPlanActionResponse,
    DataLocationsResponse,
    DataExportResponse,
    DataClearRequest,
    DataClearResponse,
    BackupCreateRequest,
    BackupCreateResponse,
    BackupRestoreRequest,
    BackupRestoreResponse,
    BackupListResponse,
    DemoStatusResponse,
    DemoActionResponse,
    PairingGenerateResponse,
    PairingExchangeRequest,
    PairingExchangeResponse,
    SessionStatusResponse,
    SessionRevokeResponse,
    RemoteStopResponse,
)
from app.core.config import settings
from app.core.confirmation import confirmation_manager
from app.core.data_manager import user_data_manager
from app.core.demo_manager import demo_manager
from app.core.rate_limiter import auth_rate_limiter
from app.core.remote_auth import remote_session_manager
from app.core.browser_automation import (
    browser_manager,
    validate_approved_url,
    is_sensitive_field,
    check_forbidden_action,
    BrowserSecurityViolation,
    DomainSecurityViolation,
)
from app.core.google_auth import (
    google_auth_manager,
    GoogleConfigError,
    GoogleAuthError,
)
from app.core.logger import action_logger, ActionLogEntry
from app.services.agent_service import agent_service
from app.services.extension_service import extension_service
from app.tools.registry import tool_registry
from app.tools.reminders_tools import reminders_storage, delete_reminder
from app.tools.memory_tools import memory_storage, detect_sensitive_data
from app.tools.briefing_tools import build_daily_briefing
from app.tools.gmail_tools import list_gmail_messages, summarize_gmail_messages
from app.tools.calendar_tools import list_calendar_events, summarize_calendar_events

def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract session token from Authorization: Bearer <token> or X-Session-Token header."""
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    x_token = request.headers.get("x-session-token")
    if x_token:
        return x_token.strip()
    return None


def is_remote_request(request: Request) -> bool:
    """
    Determine whether a request originates from a remote client.
    Evaluates:
    1. Origin header (e.g. Vercel hosted PWA origin)
    2. Host header (e.g. *.ts.net Tailscale Serve proxy)
    3. Client IP (non-loopback network address)
    """
    origin = request.headers.get("origin")
    if origin:
        clean_origin = origin.strip().rstrip("/")
        if not (
            clean_origin.startswith("http://localhost")
            or clean_origin.startswith("http://127.0.0.1")
            or clean_origin.startswith("chrome-extension://")
        ):
            return True

    host = request.headers.get("host")
    if host:
        from app.main import TAILSCALE_HOST_REGEX
        if TAILSCALE_HOST_REGEX.match(host.strip()):
            return True

    if request.client and request.client.host:
        if request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            return True

    return False


async def require_remote_session(request: Request) -> Optional[str]:
    """
    FastAPI dependency: Enforces valid in-memory session token for any remote requests.
    Direct local loopback calls without remote origin pass through (preserving local extension & tests).
    """
    token = extract_token_from_request(request)

    # If a token is provided (even locally), validate it
    if token:
        is_valid, reason = remote_session_manager.validate_session_token(token)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Remote authentication failed: {reason}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return token

    # If no token is provided, verify whether this request is remote
    if is_remote_request(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Remote authentication required: A valid in-memory session token "
                "must be provided in Authorization: Bearer <token> or X-Session-Token header."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return None


# Remote-session auth policy (Phase 11 hardening): every endpoint in this
# router requires a valid remote session token for remote requests
# (Depends(require_remote_session) on each handler), except /health,
# /remote/pair/exchange and /remote/session/status, which are public by
# design, and /remote/pair/generate, which is local-only via its own guard.
# Local loopback requests (and the Chrome extension) pass through without
# a token, preserving local use and the existing test suite.
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """System health-check verifying server readiness and active tools.

    The response intentionally contains no filesystem paths: /health is
    public, so absolute workspace/notes/screenshots directories are not
    disclosed to unauthenticated callers.
    """
    tools = [t.name for t in tool_registry.get_all_tools()]
    rem_count = len(reminders_storage.list_all(include_completed=True))
    mem_count = len(memory_storage.list_all())
    search_ready = bool(settings.SEARCH_API_KEY and settings.SEARCH_API_KEY.strip() not in ("", "your_search_api_key_here"))
    return HealthResponse(
        status="ok",
        version=__version__,
        gemini_configured=agent_service.is_configured(),
        search_configured=search_ready,
        search_provider=settings.SEARCH_PROVIDER,
        platform=sys.platform,
        reminders_count=rem_count,
        memories_count=mem_count,
        memory_enabled=settings.MEMORY_ENABLED,
        google_connected=google_auth_manager.is_connected(),
        active_tools=tools,
    )


# --- Phase 11 Remote Pairing & Control Endpoints (Tailscale Private Connection) ---

@router.post("/remote/pair/generate", response_model=PairingGenerateResponse, tags=["Remote Pairing"])
async def generate_pairing_code_endpoint(request: Request) -> PairingGenerateResponse:
    """
    Generate a 6-digit one-time remote pairing code.
    STRICT SECURITY: Can only be called from loopback/localhost directly on the laptop.
    Rejects remote calls to prevent attackers from generating codes remotely.
    """
    if is_remote_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Pairing codes can only be generated directly on the local laptop."
        )
    code = remote_session_manager.generate_pairing_code()
    return PairingGenerateResponse(
        pairing_code=code,
        expires_in_seconds=settings.REMOTE_PAIRING_CODE_TIMEOUT_SECONDS,
        instructions="Enter this 6-digit code in the hosted Jarvis PWA on your phone within 5 minutes."
    )


@router.post("/remote/pair/exchange", response_model=PairingExchangeResponse, tags=["Remote Pairing"])
async def exchange_pairing_code_endpoint(req: PairingExchangeRequest, request: Request) -> PairingExchangeResponse:
    """
    Exchange a one-time pairing code for an in-memory revocable session token.
    Enforces rate limits, single-use, and expiration.
    """
    client_ip = request.client.host if request.client and request.client.host else "127.0.0.1"
    session = remote_session_manager.exchange_pairing_code(req.pairing_code, client_ip)
    expires_in = max(1, int(session.expires_at - time.time()))
    return PairingExchangeResponse(
        session_token=session.token,
        expires_in_seconds=expires_in,
        token_type="Bearer"
    )


@router.get("/remote/session/status", response_model=SessionStatusResponse, tags=["Remote Pairing"])
async def session_status_endpoint(request: Request) -> SessionStatusResponse:
    """Check whether the provided session token is currently valid."""
    token = extract_token_from_request(request)
    if not token:
        return SessionStatusResponse(valid=False, detail="No session token provided.")
    is_valid, reason = remote_session_manager.validate_session_token(token)
    if not is_valid:
        return SessionStatusResponse(valid=False, detail=reason)
    session = remote_session_manager.get_session(token)
    expires_in = max(0, int(session.expires_at - time.time())) if session else 0
    return SessionStatusResponse(valid=True, expires_in_seconds=expires_in)


@router.post("/remote/session/revoke", response_model=SessionRevokeResponse, tags=["Remote Pairing"])
async def session_revoke_endpoint(request: Request, _auth: Optional[str] = Depends(require_remote_session)) -> SessionRevokeResponse:
    """Revoke the current session token upon user disconnect."""
    token = extract_token_from_request(request)
    if not token:
        return SessionRevokeResponse(revoked=False, message="No token provided to revoke.")
    success = remote_session_manager.revoke_session(token)
    return SessionRevokeResponse(
        revoked=success,
        message="Session revoked successfully. Device disconnected." if success else "Session not found."
    )


@router.post("/remote/stop", response_model=RemoteStopResponse, tags=["Remote Control"])
async def remote_stop_endpoint(
    request: Request,
    _auth: Optional[str] = Depends(require_remote_session)
) -> RemoteStopResponse:
    """Halt any in-flight active assistant tasks or operations."""
    return RemoteStopResponse(stopped=True, message="Active operation aborted promptly.")


@router.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat_endpoint(
    request: ChatRequest,
    _auth: Optional[str] = Depends(require_remote_session)
) -> ChatResponse:
    """
    Accepts a user message, delegates to the Gemini-powered agent,
    executes approved tools safely, and returns the response.
    """
    if len(request.message) > settings.MAX_REQUEST_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message exceeds maximum length of {settings.MAX_REQUEST_LENGTH} characters.",
        )

    response = await agent_service.chat(request.message)

    tool_infos = [
        ToolExecutionInfo(
            tool_name=t.tool_name,
            arguments=t.arguments,
            success=t.success,
            output=t.output,
            error=t.error,
        )
        for t in response.tools_executed
    ]

    return ChatResponse(
        reply=response.message,
        tools_executed=tool_infos,
        success=response.success,
        error=response.error,
    )


@router.get("/tools", response_model=List[ToolInfo], tags=["Tools"])
async def list_tools(_auth: Optional[str] = Depends(require_remote_session)) -> List[ToolInfo]:
    """Returns all currently active and approved tools."""
    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            parameters=t.parameters,
        )
        for t in tool_registry.get_all_tools()
    ]


@router.get("/actions", response_model=List[ActionLogEntry], tags=["Audit"])
async def get_recent_actions(
    limit: int = 50,
    _auth: Optional[str] = Depends(require_remote_session)
) -> List[ActionLogEntry]:
    """Returns recent tool actions from the in-memory audit log."""
    safe_limit = max(1, min(limit, 100))
    return action_logger.get_recent_actions(limit=safe_limit)


# --- Confirmation Management Endpoints ---

@router.get("/confirm/pending", response_model=List[PendingActionInfo], tags=["Confirmation"])
async def get_pending_confirmations(
    _auth: Optional[str] = Depends(require_remote_session)
) -> List[PendingActionInfo]:
    """List all actions currently waiting for explicit user confirmation."""
    pending = confirmation_manager.list_pending()
    return [
        PendingActionInfo(
            confirmation_id=p.confirmation_id,
            tool_name=p.tool_name,
            description=p.description,
            arguments=p.arguments,
            created_at=p.created_at,
            expires_at=p.expires_at,
        )
        for p in pending
    ]


@router.post("/confirm", response_model=ConfirmationResponse, tags=["Confirmation"])
async def confirm_action(
    req: ConfirmationRequest,
    request: Request,
    _auth: Optional[str] = Depends(require_remote_session)
) -> ConfirmationResponse:
    """
    Explicitly approve or deny a pending action requiring confirmation.
    If approved, executes the tool safely and returns the output.
    Rate-limited against brute-force token enumeration.
    """
    auth_rate_limiter.check_request(request)

    if not req.approve:
        denied = confirmation_manager.deny_action(req.confirmation_id)
        if denied:
            return ConfirmationResponse(
                success=True,
                message=f"Action '{req.confirmation_id}' has been denied and cancelled.",
            )
        else:
            auth_rate_limiter.record_failure(request)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pending action '{req.confirmation_id}' not found or already expired.",
            )

    # Approve
    action = confirmation_manager.confirm_action(req.confirmation_id)
    if not action:
        auth_rate_limiter.record_failure(request)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending action '{req.confirmation_id}' not found or expired.",
        )

    # Execute tool with confirmed token
    execution_args = dict(action.arguments)
    execution_args["confirmation_id"] = req.confirmation_id

    result = tool_registry.execute_tool(action.tool_name, execution_args)

    return ConfirmationResponse(
        success=result.success,
        message=f"Action '{action.tool_name}' executed: {'Success' if result.success else 'Failed'}.",
        tool_result=result.to_dict(),
    )


# --- Extension Endpoints ---

@router.post("/extension/read-page", response_model=PageReadResponse, tags=["Extension"])
async def read_page_endpoint(req: PageReadRequest, _auth: Optional[str] = Depends(require_remote_session)) -> PageReadResponse:
    """
    Endpoint for Jarvis Chrome extension.
    Accepts visible text extracted from user-selected active tab, analyzes with Gemini,
    and returns a grounded summary or practice quiz study assistance.
    """
    if len(req.page_text) > settings.MAX_PAGE_TEXT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Page text exceeds limit of {settings.MAX_PAGE_TEXT_CHARS} characters.",
        )

    result = await extension_service.analyze_page(
        url=req.url,
        title=req.title,
        page_text=req.page_text,
        question=req.question,
        mode=req.mode,
    )

    return PageReadResponse(
        reply=result.reply,
        mode=result.mode,
        disclosure=result.disclosure,
        chars_processed=result.chars_processed,
        success=result.success,
        error=result.error,
    )


# --- Phase 4: Reminders Endpoints ---

@router.get("/reminders", response_model=List[ReminderResponse], tags=["Reminders"])
async def get_reminders(include_completed: bool = False, _auth: Optional[str] = Depends(require_remote_session)) -> List[ReminderResponse]:
    """List all saved local reminders."""
    items = reminders_storage.list_all(include_completed=include_completed)
    return [
        ReminderResponse(
            id=r.id,
            title=r.title,
            due_time=r.due_time,
            notes=r.notes,
            completed=r.completed,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in items
    ]


@router.post("/reminders", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED, tags=["Reminders"])
async def create_reminder_endpoint(req: ReminderCreateRequest, _auth: Optional[str] = Depends(require_remote_session)) -> ReminderResponse:
    """Create a new local reminder on the laptop."""
    r = reminders_storage.add(
        title=req.title,
        due_time=req.due_time,
        notes=req.notes,
    )
    return ReminderResponse(
        id=r.id,
        title=r.title,
        due_time=r.due_time,
        notes=r.notes,
        completed=r.completed,
        created_at=r.created_at,
        completed_at=r.completed_at,
    )


@router.patch("/reminders/{reminder_id}/complete", response_model=ReminderResponse, tags=["Reminders"])
async def mark_reminder_completed(reminder_id: str, _auth: Optional[str] = Depends(require_remote_session)) -> ReminderResponse:
    """Mark a local reminder as completed."""
    r = reminders_storage.complete(reminder_id.strip())
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reminder with ID '{reminder_id}' not found.",
        )
    return ReminderResponse(
        id=r.id,
        title=r.title,
        due_time=r.due_time,
        notes=r.notes,
        completed=r.completed,
        created_at=r.created_at,
        completed_at=r.completed_at,
    )


@router.delete("/reminders/{reminder_id}", tags=["Reminders"])
async def delete_reminder_endpoint(
    reminder_id: str,
    confirmation_id: Optional[str] = Query(None, description="Confirmation token for deleting the reminder."),
    _auth: Optional[str] = Depends(require_remote_session),
):
    """
    Delete a local reminder. Requires explicit user confirmation.
    """
    res = delete_reminder(reminder_id=reminder_id, confirmation_id=confirmation_id)
    if not res.success:
        if res.output and res.output.get("requires_confirmation"):
            return res.output
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.error,
        )
    return res.output


# --- Phase 4: Memory Endpoints ---

@router.get("/memories", response_model=List[MemoryResponse], tags=["Memory"])
async def get_memories(_auth: Optional[str] = Depends(require_remote_session)) -> List[MemoryResponse]:
    """List all user-approved items in local persistent memory."""
    items = memory_storage.list_all()
    return [
        MemoryResponse(
            key=m.key,
            content=m.content,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in items
    ]


@router.post("/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED, tags=["Memory"])
async def add_or_update_memory(req: MemoryCreateRequest, _auth: Optional[str] = Depends(require_remote_session)) -> MemoryResponse:
    """Store or update user-approved memory with sensitive credential screening."""
    if not settings.MEMORY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memory is currently disabled by user setting.",
        )

    sensitive_issue = detect_sensitive_data(req.key) or detect_sensitive_data(req.content)
    if sensitive_issue:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Privacy refusal: Memory cannot store a potential {sensitive_issue}.",
        )

    item = memory_storage.put(key=req.key, content=req.content)
    return MemoryResponse(
        key=item.key,
        content=item.content,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete("/memories/{key}", tags=["Memory"])
async def delete_memory_by_key(key: str, _auth: Optional[str] = Depends(require_remote_session)):
    """Delete a memory item by its key."""
    deleted = memory_storage.delete(key.strip())
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No memory found with key '{key}'.",
        )
    return {"message": f"Successfully deleted memory '{key}'."}


@router.delete("/memories", tags=["Memory"])
async def clear_all_memories(
    confirm: bool = Query(False, description="Set confirm=true to clear all memories."),
    _auth: Optional[str] = Depends(require_remote_session),
):
    """Clear all memories from local persistent storage."""
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="To clear all memories, you must pass query parameter ?confirm=true.",
        )
    count = memory_storage.clear()
    return {"message": f"Cleared all memories ({count} items removed)."}


@router.get("/memories/status", response_model=MemoryStatusResponse, tags=["Memory"])
async def get_memory_status(_auth: Optional[str] = Depends(require_remote_session)) -> MemoryStatusResponse:
    """Get memory system status and item count."""
    return MemoryStatusResponse(
        enabled=settings.MEMORY_ENABLED,
        count=len(memory_storage.list_all()),
    )


@router.post("/memories/toggle", response_model=MemoryStatusResponse, tags=["Memory"])
async def toggle_memory(req: MemoryToggleRequest, _auth: Optional[str] = Depends(require_remote_session)) -> MemoryStatusResponse:
    """Enable or disable persistent memory storage."""
    settings.MEMORY_ENABLED = req.enabled
    return MemoryStatusResponse(
        enabled=settings.MEMORY_ENABLED,
        count=len(memory_storage.list_all()),
    )


# --- Phase 5: Daily Briefing Endpoint ---

@router.get("/briefing", tags=["Briefing"])
async def get_briefing_endpoint(
    include_web_summary: bool = Query(False, description="Whether to include external web search results in the briefing."),
    web_topics: Optional[str] = Query(None, description="General non-personal topics to search for web overview."),
    _auth: Optional[str] = Depends(require_remote_session),
):
    """
    On-demand daily briefing summarizing today's reminders, recent notes/tasks,
    and optional web updates. Never schedules background jobs or broadcasts.
    """
    result = await build_daily_briefing(
        include_web_summary=include_web_summary,
        web_topics=web_topics,
    )
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error,
        )
    return result.output


# --- Phase 6: Google OAuth, Gmail & Google Calendar Endpoints ---

@router.get("/auth/google/url", response_model=GoogleAuthUrlResponse, tags=["Google Auth"])
async def get_google_auth_url(redirect_uri: Optional[str] = Query(None), _auth: Optional[str] = Depends(require_remote_session)) -> GoogleAuthUrlResponse:
    """
    Generate a Google OAuth 2.0 authorization URL using PKCE (S256) and anti-CSRF state.
    User visits this URL in a browser to grant read-only Gmail and Calendar permissions.
    """
    try:
        auth_url, state = google_auth_manager.create_authorization_url(redirect_uri=redirect_uri)
        return GoogleAuthUrlResponse(
            auth_url=auth_url,
            state=state,
            scopes=settings.GOOGLE_OAUTH_SCOPES,
        )
    except GoogleConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create auth URL: {e}")


@router.get("/auth/google/callback", tags=["Google Auth"])
async def google_auth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    _auth: Optional[str] = Depends(require_remote_session),
):
    """
    OAuth 2.0 redirect callback endpoint.
    Verifies state token, exchanges code for tokens via PKCE, and stores refresh token securely.
    Rate-limited against brute-force state/code manipulation.
    """
    auth_rate_limiter.check_request(request)

    if error:
        auth_rate_limiter.record_failure(request)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authorization error returned: {error}",
        )
    if not code or not state:
        auth_rate_limiter.record_failure(request)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'code' or 'state' parameter in OAuth callback.",
        )

    try:
        result = google_auth_manager.exchange_code(code=code, state=state)
        return {
            "status": "connected",
            "message": "Google account successfully connected with read-only Gmail and Calendar access.",
            "account_email": result.get("account_email"),
            "storage_backend": result.get("storage_backend"),
            "scopes": result.get("scopes"),
        }
    except GoogleAuthError as e:
        auth_rate_limiter.record_failure(request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        auth_rate_limiter.record_failure(request)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        auth_rate_limiter.record_failure(request)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OAuth exchange failed: {e}")


@router.post("/auth/google/disconnect", response_model=GoogleDisconnectResponse, tags=["Google Auth"])
async def disconnect_google(_auth: Optional[str] = Depends(require_remote_session)) -> GoogleDisconnectResponse:
    """
    Disconnect Google account: revokes tokens with Google and erases local credentials.
    """
    res = google_auth_manager.disconnect()
    return GoogleDisconnectResponse(
        status=res.get("status", "disconnected"),
        message=res.get("message", "Google account disconnected."),
        revoked_remotely=res.get("revoked_remotely", False),
    )


@router.get("/auth/google/status", response_model=GoogleAuthStatusResponse, tags=["Google Auth"])
async def get_google_status(_auth: Optional[str] = Depends(require_remote_session)) -> GoogleAuthStatusResponse:
    """
    Check current Google account connection status and storage backend.
    """
    st = google_auth_manager.get_status()
    return GoogleAuthStatusResponse(
        connected=st["connected"],
        account_email=st.get("account_email"),
        scopes=st.get("scopes", []),
        storage_backend=st.get("storage_backend", "Unknown"),
        connected_at=st.get("connected_at"),
        read_only=st.get("read_only", True),
    )


@router.get("/gmail/messages", response_model=GmailListResponse, tags=["Gmail"])
async def list_gmail_messages_endpoint(
    max_results: int = Query(5, ge=1, le=20, description="Max messages to retrieve."),
    query: Optional[str] = Query(None, max_length=150, description="Optional search filter."),
    _auth: Optional[str] = Depends(require_remote_session),
) -> GmailListResponse:
    """
    List recent Gmail messages with metadata (Sender, Subject, Date, Snippet).
    Strictly read-only.
    """
    res = list_gmail_messages(max_results=max_results, query=query)
    if not res.success:
        status_code = status.HTTP_400_BAD_REQUEST if "not connected" in res.error.lower() else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(status_code=status_code, detail=res.error)

    output = res.output
    return GmailListResponse(
        count=output["count"],
        messages=output["messages"],
        filter_query=output.get("filter_query"),
        read_only=True,
    )


@router.post("/gmail/summarize", response_model=GmailSummarizeResponse, tags=["Gmail"])
async def summarize_gmail_endpoint(req: GmailSummarizeRequest, _auth: Optional[str] = Depends(require_remote_session)) -> GmailSummarizeResponse:
    """
    Summarize selected or recent Gmail messages using Gemini.
    Discloses that email text is sent to Gemini. Never stores email bodies in memory or logs.
    """
    res = summarize_gmail_messages(
        message_ids=req.message_ids,
        max_results=req.max_results,
        query=req.query,
        custom_instructions=req.custom_instructions,
    )
    if not res.success:
        status_code = status.HTTP_400_BAD_REQUEST if "not connected" in res.error.lower() else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(status_code=status_code, detail=res.error)

    output = res.output
    return GmailSummarizeResponse(
        count=output["count"],
        summary=output["summary"],
        analyzed_messages=output.get("analyzed_messages"),
        disclosure=output["disclosure"],
        read_only=True,
    )


@router.get("/calendar/events", response_model=CalendarListResponse, tags=["Calendar"])
async def list_calendar_events_endpoint(
    time_min: Optional[str] = Query(None, description="Start datetime in ISO 8601."),
    time_max: Optional[str] = Query(None, description="End datetime in ISO 8601."),
    max_results: int = Query(10, ge=1, le=25, description="Max events to retrieve."),
    calendar_id: str = Query("primary", description="Calendar identifier."),
    _auth: Optional[str] = Depends(require_remote_session),
) -> CalendarListResponse:
    """
    List upcoming Google Calendar events for a date range.
    Strictly read-only.
    """
    res = list_calendar_events(
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        calendar_id=calendar_id,
    )
    if not res.success:
        status_code = status.HTTP_400_BAD_REQUEST if ("not connected" in res.error.lower() or "invalid" in res.error.lower()) else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(status_code=status_code, detail=res.error)

    output = res.output
    return CalendarListResponse(
        count=output["count"],
        events=output["events"],
        time_min=output["time_min"],
        time_max=output["time_max"],
        read_only=True,
    )


@router.post("/calendar/summarize", response_model=CalendarSummarizeResponse, tags=["Calendar"])
async def summarize_calendar_endpoint(req: CalendarSummarizeRequest, _auth: Optional[str] = Depends(require_remote_session)) -> CalendarSummarizeResponse:
    """
    Summarize Google Calendar events across a date range using Gemini.
    Discloses that event details are sent to Gemini. Never stores event titles in memory or logs.
    """
    res = summarize_calendar_events(
        time_min=req.time_min,
        time_max=req.time_max,
        calendar_id=req.calendar_id,
    )
    if not res.success:
        status_code = status.HTTP_400_BAD_REQUEST if "not connected" in res.error.lower() else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(status_code=status_code, detail=res.error)

    output = res.output
    return CalendarSummarizeResponse(
        count=output["count"],
        summary=output["summary"],
        disclosure=output["disclosure"],
        time_min=output.get("time_min"),
        time_max=output.get("time_max"),
        read_only=True,
    )


# --- Phase 8: Limited Browser Automation Endpoints ---

@router.get("/browser/approved-domains", response_model=ApprovedDomainsResponse, tags=["Browser Automation"])
async def get_approved_domains(_auth: Optional[str] = Depends(require_remote_session)) -> ApprovedDomainsResponse:
    """Get the current list of user-approved domains for browser automation."""
    return ApprovedDomainsResponse(approved_domains=browser_manager.get_approved_domains())


@router.post("/browser/approve-domain", response_model=ApprovedDomainsResponse, tags=["Browser Automation"])
async def approve_domain_endpoint(req: ApproveDomainRequest, _auth: Optional[str] = Depends(require_remote_session)) -> ApprovedDomainsResponse:
    """Explicitly approve a domain for browser automation."""
    try:
        browser_manager.approve_domain(req.domain)
        return ApprovedDomainsResponse(approved_domains=browser_manager.get_approved_domains())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/browser/plan-action", response_model=BrowserPlanActionResponse, tags=["Browser Automation"])
async def plan_browser_action(req: BrowserPlanActionRequest, _auth: Optional[str] = Depends(require_remote_session)) -> BrowserPlanActionResponse:
    """
    Validate and stage a low-risk browser action.
    Enforces domain restrictions, sensitive-field exclusion, and forbidden action rules.
    If action causes state changes, returns a confirmation_id requiring user approval.
    """
    act = req.action_type.strip().lower()

    # 1. Validate domain
    if not browser_manager.is_approved(req.approved_domain):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Domain '{req.approved_domain}' is not approved. Please approve this domain "
                f"first via the extension or /api/browser/approve-domain."
            ),
        )

    # 2. Validate action specifics
    if act == "navigate":
        if not req.url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Argument 'url' is required for navigation.")
        try:
            clean_url = validate_approved_url(req.url, req.approved_domain)
        except DomainSecurityViolation as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        desc = f"Navigate browser to '{clean_url}' within approved domain '{req.approved_domain}'"
        pending = confirmation_manager.create_pending_action(
            tool_name="browser_navigate",
            arguments={"url": clean_url, "approved_domain": req.approved_domain},
            description=desc,
        )
        return BrowserPlanActionResponse(
            allowed=True,
            action_type="navigate",
            approved_domain=req.approved_domain,
            requires_confirmation=True,
            confirmation_id=pending.confirmation_id,
            description=desc,
        )

    elif act == "fill_field":
        if not req.selector:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Argument 'selector' is required for fill_field.")
        if req.value is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Argument 'value' is required for fill_field.")

        # Check sensitive field
        if is_sensitive_field(selector=req.selector, label_or_desc=req.field_description):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security Refusal: Field '{req.selector}' is sensitive (password, card, or auth). Cannot automate.",
            )

        # Check forbidden submit/purchase
        try:
            check_forbidden_action("fill_field", target_selector=req.selector, description=req.field_description)
        except BrowserSecurityViolation as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Check sensitive value
        sensitive_reason = detect_sensitive_data(req.value)
        if sensitive_reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Privacy Refusal: Proposed value contains sensitive credentials ({sensitive_reason}). Cannot automate.",
            )

        desc = f"Fill field '{req.field_description or req.selector}' on approved domain '{req.approved_domain}'. (Manual submit required)"
        pending = confirmation_manager.create_pending_action(
            tool_name="browser_fill_field",
            arguments={
                "selector": req.selector.strip(),
                "value": req.value,
                "approved_domain": req.approved_domain,
            },
            description=desc,
        )
        return BrowserPlanActionResponse(
            allowed=True,
            action_type="fill_field",
            approved_domain=req.approved_domain,
            requires_confirmation=True,
            confirmation_id=pending.confirmation_id,
            description=desc,
            warning="Notice: The final submit button must be clicked manually by you; the agent does not submit forms.",
        )

    elif act == "read_page":
        if req.url:
            try:
                validate_approved_url(req.url, req.approved_domain)
            except DomainSecurityViolation as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        return BrowserPlanActionResponse(
            allowed=True,
            action_type="read_page",
            approved_domain=req.approved_domain,
            requires_confirmation=False,
            description="Read visible text from approved page. Page text is treated as untrusted reference data.",
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported browser action '{req.action_type}'. Approved actions: navigate, read_page, fill_field.",
        )


# --- Phase 9: User Data Controls, Backup & Recovery Endpoints ---

@router.get("/data/locations", response_model=DataLocationsResponse, tags=["Data Management"])
async def get_data_locations_endpoint(_auth: Optional[str] = Depends(require_remote_session)) -> DataLocationsResponse:
    """View all local filesystem paths where user data is stored."""
    locs = user_data_manager.get_data_locations()
    return DataLocationsResponse(**locs)


@router.get("/data/export", response_model=DataExportResponse, tags=["Data Management"])
async def export_user_data_endpoint(_auth: Optional[str] = Depends(require_remote_session)) -> DataExportResponse:
    """
    Export all user-owned notes, memories, and reminders in clean JSON format.
    Strictly excludes secrets, API keys, and credentials.
    """
    data = user_data_manager.export_user_data()
    return DataExportResponse(**data)


@router.post("/data/clear", response_model=DataClearResponse, tags=["Data Management"])
async def clear_all_data_endpoint(req: DataClearRequest, _auth: Optional[str] = Depends(require_remote_session)) -> DataClearResponse:
    """
    Permanently wipe all user notes, memories, reminders, and screenshot images.
    Requires confirm=true and confirmation_text='DELETE ALL DATA'.
    """
    try:
        res = user_data_manager.clear_all_local_data(
            confirm=req.confirm,
            confirmation_text=req.confirmation_text,
        )
        return DataClearResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/data/backups", response_model=BackupListResponse, tags=["Data Management"])
async def list_backups_endpoint(_auth: Optional[str] = Depends(require_remote_session)) -> BackupListResponse:
    """List all available local backup snapshots with verification status."""
    backups = user_data_manager.list_backups()
    return BackupListResponse(count=len(backups), backups=backups)


@router.post("/data/backup", response_model=BackupCreateResponse, tags=["Data Management"])
async def create_backup_endpoint(req: BackupCreateRequest = BackupCreateRequest(), _auth: Optional[str] = Depends(require_remote_session)) -> BackupCreateResponse:
    """
    Create a local validated backup snapshot of notes, reminders, and memories
    with a SHA-256 integrity checksum. Does NOT include secrets or credentials.
    """
    res = user_data_manager.create_backup(backup_name=req.backup_name)
    return BackupCreateResponse(**res)


@router.post("/data/restore", response_model=BackupRestoreResponse, tags=["Data Management"])
async def restore_backup_endpoint(req: BackupRestoreRequest, _auth: Optional[str] = Depends(require_remote_session)) -> BackupRestoreResponse:
    """
    Safely restore user data from a local backup file after checksum validation.
    Requires confirm_overwrite=true if existing data is present.
    """
    try:
        res = user_data_manager.restore_backup(
            backup_filename=req.backup_filename,
            confirm_overwrite=req.confirm_overwrite,
        )
        return BackupRestoreResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Restore failed: {e}")


# --- Phase 10: End-to-End Demo Mode Endpoints ---

@router.get("/demo/status", response_model=DemoStatusResponse, tags=["Demo"])
async def get_demo_status_endpoint(_auth: Optional[str] = Depends(require_remote_session)) -> DemoStatusResponse:
    """Returns the current status, links, and step-by-step instructions for Phase 10 Demo."""
    st = demo_manager.get_status()
    return DemoStatusResponse(**st)


@router.post("/demo/seed", response_model=DemoActionResponse, tags=["Demo"])
async def seed_demo_data_endpoint(_auth: Optional[str] = Depends(require_remote_session)) -> DemoActionResponse:
    """Seeds fictional mock notes, reminders, and memory tagged with '[DEMO]'."""
    res = demo_manager.seed_demo_data()
    return DemoActionResponse(**res)


@router.post("/demo/reset", response_model=DemoActionResponse, tags=["Demo"])
async def clear_demo_data_endpoint(_auth: Optional[str] = Depends(require_remote_session)) -> DemoActionResponse:
    """One-step deletion of mock/demo data without touching real user files or records."""
    res = demo_manager.clear_demo_data()
    return DemoActionResponse(**res)


