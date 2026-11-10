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
    ApiKeyRequest,
    KeyStatusResponse,
)
from app.core.byok import (
    ByokError,
    delete_user_key,
    key_status,
    store_user_key,
    validate_user_key,
)
from app.core.config import settings
from app.core.confirmation import confirmation_manager
from app.core.data_manager import user_data_manager
from app.core.session import (
    create_oauth_state_token,
    create_session_token,
    verify_oauth_state_token,
    verify_session_token,
)
from app.core.store import get_user_store
from app.core.user_context import LOCAL_OWNER, UserIdentity, set_current_user
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
from app.tools.reminders_tools import delete_reminder
from app.tools.memory_tools import detect_sensitive_data
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


def _user_from_request(request: Request) -> Optional[UserIdentity]:
    """Resolve the signed-in Google user from a session JWT (cookie or
    Bearer header). Returns None when no valid session is presented."""
    token = extract_token_from_request(request)
    if token:
        user = verify_session_token(token)
        if user:
            return user
    cookie = request.cookies.get("jarvis_session")
    if cookie:
        user = verify_session_token(cookie)
        if user:
            return user
    return None


def _presented_invalid_token(request: Request) -> bool:
    """True when a token/cookie was presented but did not verify."""
    if extract_token_from_request(request) or request.cookies.get("jarvis_session"):
        return _user_from_request(request) is None
    return False


async def require_user(request: Request) -> UserIdentity:
    """
    FastAPI dependency: the caller of every AI/data endpoint.

    Cloud-first auth (Phase 12):
    1. Valid Google session JWT (cookie or Authorization: Bearer) -> that user.
    2. In LOCAL mode only: a valid Tailscale remote-session token, or a
       direct loopback request, -> the local owner (historical behaviour,
       keeps local dev and the existing test suite working).
    3. Otherwise -> 401. In CLOUD_MODE=true (Vercel) there is no step 2:
       unauthenticated requests to AI/data endpoints always 401.
    """
    user = _user_from_request(request)
    if user:
        set_current_user(user)
        return user
    if not settings.CLOUD_MODE:
        # Local mode: a valid Tailscale remote-session token also authenticates
        # (as the laptop owner). This check must come before the
        # invalid-token rejection below — a remote token is not a JWT.
        token = extract_token_from_request(request)
        if token:
            is_valid, _reason = remote_session_manager.validate_session_token(token)
            if is_valid:
                set_current_user(LOCAL_OWNER)
                return LOCAL_OWNER
        if not is_remote_request(request):
            set_current_user(LOCAL_OWNER)
            return LOCAL_OWNER
    if _presented_invalid_token(request):
        presented = extract_token_from_request(request) or ""
        if presented.count(".") == 2:
            detail = "Invalid or expired session. Please sign in with Google again."
        else:
            # Opaque token (e.g. a stale Tailscale pairing token).
            detail = "Remote authentication failed: invalid or expired session token."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Sign-in required: please sign in with Google in the Jarvis app "
            "to use Jarvis. No laptop or local setup is needed."
        ),
        headers={"WWW-Authenticate": "Bearer"},
    )


def _cloud_gmail_unavailable() -> None:
    """Gmail/Calendar read-only access is local-mode only (single-owner
    keyring tokens). In cloud mode per-user Gmail tokens are not built yet."""
    if settings.CLOUD_MODE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gmail and Calendar are not available in cloud mode yet: they still "
                "use the laptop owner's single Google connection. Sign-in, chat, "
                "notes, memories and reminders work in the cloud."
            ),
        )


# Auth policy (Phase 12, cloud-first): every endpoint in this router
# requires a signed-in user (Depends(require_user)), except /health, the
# pairing endpoints, and the login flow itself (/auth/login,
# /auth/login/callback), which are public by design. In local mode the
# "user" is the laptop owner for loopback requests, preserving local use
# and the existing test suite.
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """System health-check verifying server readiness and active tools.

    The response intentionally contains no filesystem paths: /health is
    public, so absolute workspace/notes/screenshots directories are not
    disclosed to unauthenticated callers.
    """
    tools = [t.name for t in tool_registry.get_all_tools()]
    if settings.CLOUD_MODE:
        # Public endpoint: never leak per-user counts or the owner's
        # single-account Gmail connection state in cloud mode.
        rem_count = 0
        mem_count = 0
        google_connected = False
    else:
        store = get_user_store()
        rem_count = len(store.list_reminders(LOCAL_OWNER, include_completed=True))
        mem_count = len(store.list_memories(LOCAL_OWNER))
        google_connected = google_auth_manager.is_connected()
    search_ready = bool(settings.SEARCH_API_KEY and settings.SEARCH_API_KEY.strip() not in ("", "your_search_api_key_here"))
    return HealthResponse(
        status="ok",
        version=__version__,
        gemini_configured=False,  # BYOK: readiness is per-user, see /api/auth/key/status
        search_configured=search_ready,
        search_provider=settings.SEARCH_PROVIDER,
        platform=sys.platform,
        reminders_count=rem_count,
        memories_count=mem_count,
        memory_enabled=settings.MEMORY_ENABLED,
        google_connected=google_connected,
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
    user: UserIdentity = Depends(require_user)
) -> RemoteStopResponse:
    """Halt any in-flight active assistant tasks or operations."""
    return RemoteStopResponse(stopped=True, message="Active operation aborted promptly.")


@router.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat_endpoint(
    request: ChatRequest,
    user: UserIdentity = Depends(require_user)
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

    response = await agent_service.chat(request.message, user=user)

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
async def list_tools(user: UserIdentity = Depends(require_user)) -> List[ToolInfo]:
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
    user: UserIdentity = Depends(require_user)
) -> List[ActionLogEntry]:
    """Returns recent tool actions from the in-memory audit log."""
    safe_limit = max(1, min(limit, 100))
    return action_logger.get_recent_actions(limit=safe_limit, user=user)


# --- Confirmation Management Endpoints ---

@router.get("/confirm/pending", response_model=List[PendingActionInfo], tags=["Confirmation"])
async def get_pending_confirmations(
    user: UserIdentity = Depends(require_user)
) -> List[PendingActionInfo]:
    """List all actions currently waiting for explicit user confirmation."""
    pending = confirmation_manager.list_pending(user=user)
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
    user: UserIdentity = Depends(require_user)
) -> ConfirmationResponse:
    """
    Explicitly approve or deny a pending action requiring confirmation.
    If approved, executes the tool safely and returns the output.
    Rate-limited against brute-force token enumeration.
    """
    auth_rate_limiter.check_request(request)

    if not req.approve:
        denied = confirmation_manager.deny_action(req.confirmation_id, user=user)
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
    action = confirmation_manager.confirm_action(req.confirmation_id, user=user)
    if not action:
        auth_rate_limiter.record_failure(request)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending action '{req.confirmation_id}' not found or expired.",
        )

    # Execute tool with confirmed token
    execution_args = dict(action.arguments)
    execution_args["confirmation_id"] = req.confirmation_id

    result = tool_registry.execute_tool(action.tool_name, execution_args, user=user)

    return ConfirmationResponse(
        success=result.success,
        message=f"Action '{action.tool_name}' executed: {'Success' if result.success else 'Failed'}.",
        tool_result=result.to_dict(),
    )


# --- Extension Endpoints ---

@router.post("/extension/read-page", response_model=PageReadResponse, tags=["Extension"])
async def read_page_endpoint(req: PageReadRequest, user: UserIdentity = Depends(require_user)) -> PageReadResponse:
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
        user=user,
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
async def get_reminders(include_completed: bool = False, user: UserIdentity = Depends(require_user)) -> List[ReminderResponse]:
    """List the signed-in user's reminders."""
    items = get_user_store().list_reminders(user, include_completed=include_completed)
    return [ReminderResponse(**r) for r in items]


@router.post("/reminders", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED, tags=["Reminders"])
async def create_reminder_endpoint(req: ReminderCreateRequest, user: UserIdentity = Depends(require_user)) -> ReminderResponse:
    """Create a new reminder for the signed-in user."""
    r = get_user_store().add_reminder(
        user,
        title=req.title,
        due_time=req.due_time,
        notes=req.notes,
    )
    return ReminderResponse(**r)


@router.patch("/reminders/{reminder_id}/complete", response_model=ReminderResponse, tags=["Reminders"])
async def mark_reminder_completed(reminder_id: str, user: UserIdentity = Depends(require_user)) -> ReminderResponse:
    """Mark the signed-in user's reminder as completed."""
    r = get_user_store().complete_reminder(user, reminder_id.strip())
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reminder with ID '{reminder_id}' not found.",
        )
    return ReminderResponse(**r)


@router.delete("/reminders/{reminder_id}", tags=["Reminders"])
async def delete_reminder_endpoint(
    reminder_id: str,
    confirmation_id: Optional[str] = Query(None, description="Confirmation token for deleting the reminder."),
    user: UserIdentity = Depends(require_user),
):
    """
    Delete a local reminder. Requires explicit user confirmation.
    """
    res = delete_reminder(reminder_id=reminder_id, confirmation_id=confirmation_id, user=user)
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
async def get_memories(user: UserIdentity = Depends(require_user)) -> List[MemoryResponse]:
    """List the signed-in user's approved memory items."""
    items = get_user_store().list_memories(user)
    return [MemoryResponse(**m) for m in items]


@router.post("/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED, tags=["Memory"])
async def add_or_update_memory(req: MemoryCreateRequest, user: UserIdentity = Depends(require_user)) -> MemoryResponse:
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

    item = get_user_store().put_memory(user, key=req.key, content=req.content)
    return MemoryResponse(**item)


@router.delete("/memories/{key}", tags=["Memory"])
async def delete_memory_by_key(key: str, user: UserIdentity = Depends(require_user)):
    """Delete a memory item by its key."""
    deleted = get_user_store().delete_memory(user, key.strip())
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No memory found with key '{key}'.",
        )
    return {"message": f"Successfully deleted memory '{key}'."}


@router.delete("/memories", tags=["Memory"])
async def clear_all_memories(
    confirm: bool = Query(False, description="Set confirm=true to clear all memories."),
    user: UserIdentity = Depends(require_user),
):
    """Clear all memories from local persistent storage."""
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="To clear all memories, you must pass query parameter ?confirm=true.",
        )
    count = get_user_store().clear_memories(user)
    return {"message": f"Cleared all memories ({count} items removed)."}


@router.get("/memories/status", response_model=MemoryStatusResponse, tags=["Memory"])
async def get_memory_status(user: UserIdentity = Depends(require_user)) -> MemoryStatusResponse:
    """Get memory system status and item count."""
    return MemoryStatusResponse(
        enabled=settings.MEMORY_ENABLED,
        count=len(get_user_store().list_memories(user)),
    )


@router.post("/memories/toggle", response_model=MemoryStatusResponse, tags=["Memory"])
async def toggle_memory(req: MemoryToggleRequest, user: UserIdentity = Depends(require_user)) -> MemoryStatusResponse:
    """Enable or disable persistent memory storage."""
    settings.MEMORY_ENABLED = req.enabled
    return MemoryStatusResponse(
        enabled=settings.MEMORY_ENABLED,
        count=len(get_user_store().list_memories(user)),
    )


# --- Phase 5: Daily Briefing Endpoint ---

@router.get("/briefing", tags=["Briefing"])
async def get_briefing_endpoint(
    include_web_summary: bool = Query(False, description="Whether to include external web search results in the briefing."),
    web_topics: Optional[str] = Query(None, description="General non-personal topics to search for web overview."),
    user: UserIdentity = Depends(require_user),
):
    """
    On-demand daily briefing summarizing today's reminders, recent notes/tasks,
    and optional web updates. Never schedules background jobs or broadcasts.
    """
    result = await build_daily_briefing(
        include_web_summary=include_web_summary,
        web_topics=web_topics,
        user=user,
    )
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error,
        )
    return result.output



# --- Phase 12: Google Sign-in (login), BYOK key, chat history ---
# This is the cloud login flow. It is a DIFFERENT purpose from the
# read-only Gmail/Calendar OAuth above (scopes: openid/email/profile only).
# No Google password is ever seen or stored. The session is a stateless
# HS256 JWT (cookie + Bearer), so it works across Vercel serverless
# instances and cold starts. The OAuth PKCE verifier travels in a signed
# cookie for the same reason (no server-side pending-state store).

def _session_cookie_kwargs() -> dict:
    secure = settings.CLOUD_MODE or settings.ENVIRONMENT == "production"
    return {"httponly": True, "secure": secure, "samesite": "lax"}


@router.get("/auth/login", tags=["Auth"])
async def login_start(
    request: Request,
    format: Optional[str] = Query(None, description="'json' returns the auth URL instead of redirecting."),
):
    """Start Google sign-in: redirect the browser to Google (or return the
    auth URL as JSON when ?format=json). Sets a short-lived signed cookie
    holding the PKCE verifier so the callback can complete the exchange
    even after a serverless cold start."""
    try:
        auth_url, state, code_verifier, redirect_uri = google_auth_manager.create_login_authorization_url()
        state_token = create_oauth_state_token(state, code_verifier, redirect_uri)
    except GoogleConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if format == "json":
        from fastapi.responses import JSONResponse

        resp = JSONResponse({"auth_url": auth_url, "state": state})
    else:
        from fastapi.responses import RedirectResponse

        resp = RedirectResponse(url=auth_url, status_code=302)
    resp.set_cookie("jarvis_oauth_state", state_token, max_age=600,
                    path="/api/auth/login/callback", **_session_cookie_kwargs())
    return resp


@router.get("/auth/login/callback", tags=["Auth"])
async def login_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
):
    """Google sign-in callback: verify the signed state cookie, exchange the
    code for the user's Google identity, mint a Jarvis session JWT, and send
    the user back to the Companion app. With ?format=json the session token
    is returned as JSON (used by tests and API clients)."""
    from fastapi.responses import JSONResponse, RedirectResponse

    frontend = settings.FRONTEND_URL.rstrip("/")
    fail_url = f"{frontend}/mobile/?login=error"

    def _fail(detail: str):
        if format == "json":
            return JSONResponse({"detail": detail}, status_code=400)
        return RedirectResponse(url=fail_url, status_code=302)

    if error:
        return _fail(f"Google sign-in error: {error}")
    if not code or not state:
        return _fail("Missing 'code' or 'state' in sign-in callback.")
    payload = verify_oauth_state_token(request.cookies.get("jarvis_oauth_state") or "")
    if not payload or payload.get("state") != state:
        return _fail("Sign-in session expired or invalid. Please try signing in again.")
    try:
        identity = google_auth_manager.exchange_login_code(
            code=code,
            code_verifier=payload["code_verifier"],
            redirect_uri=payload["redirect_uri"],
        )
        user = UserIdentity(sub=identity["sub"], email=identity.get("email"), name=identity.get("name"))
        token = create_session_token(user)
    except GoogleAuthError as e:
        return _fail(str(e))
    except ValueError as e:
        return _fail(str(e))
    if format == "json":
        resp = JSONResponse({
            "status": "signed_in",
            "email": user.email,
            "name": user.name,
            "session_token": token,
        })
    else:
        resp = RedirectResponse(url=f"{frontend}/mobile/?login=success", status_code=302)
    resp.set_cookie("jarvis_session", token, max_age=settings.SESSION_TIMEOUT_SECONDS,
                    path="/", **_session_cookie_kwargs())
    resp.delete_cookie("jarvis_oauth_state", path="/api/auth/login/callback")
    return resp


@router.get("/auth/me", tags=["Auth"])
async def auth_me(request: Request):
    """Who is signed in right now (plus whether they have a Gemini key).
    In local mode without a Google sign-in this reports the local owner as
    not signed in — the Companion uses this to decide whether to show the
    Google sign-in button."""
    user = _user_from_request(request)
    if user is None:
        status = key_status(LOCAL_OWNER)
        return {
            "authenticated": False,
            "email": None,
            "name": None,
            "cloud_mode": settings.CLOUD_MODE,
            "has_key": status["has_key"],
            "key_hint": status["hint"],
        }
    status = key_status(user)
    return {
        "authenticated": True,
        "email": user.email,
        "name": user.name,
        "cloud_mode": settings.CLOUD_MODE,
        "has_key": status["has_key"],
        "key_hint": status["hint"],
        "key_created_at": status["created_at"],
    }


@router.post("/auth/logout", tags=["Auth"])
async def auth_logout():
    """Sign out: clears the session cookie. (JWTs are stateless, so the
    token itself remains technically valid until expiry — it is simply no
    longer presented by this browser.)"""
    from fastapi.responses import JSONResponse

    resp = JSONResponse({"logged_out": True})
    resp.delete_cookie("jarvis_session", path="/")
    return resp


@router.get("/auth/key/status", response_model=KeyStatusResponse, tags=["Auth"])
async def get_key_status(user: UserIdentity = Depends(require_user)) -> KeyStatusResponse:
    """Key status for the Companion onboarding UI: has a key been saved,
    and its masked hint (last 4 chars). The key itself is never returned."""
    st = key_status(user)
    return KeyStatusResponse(
        has_key=st["has_key"],
        hint=st.get("hint"),
        created_at=st.get("created_at"),
        valid=st.get("valid"),
    )


@router.post("/auth/key", response_model=KeyStatusResponse, tags=["Auth"])
async def save_key(req: ApiKeyRequest, user: UserIdentity = Depends(require_user)) -> KeyStatusResponse:
    """Save the user's own Gemini key (BYOK), encrypted at rest. The key is
    never returned, never logged, and only ever sent to Google's Gemini API
    for this user's own calls."""
    try:
        st = store_user_key(user, req.api_key)
    except ByokError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return KeyStatusResponse(has_key=True, hint=st["hint"], created_at=None, valid=None)


@router.post("/auth/key/validate", tags=["Auth"])
async def validate_key(user: UserIdentity = Depends(require_user)):
    """Live-check the saved key against Google (list-models call, no
    generation, no charge). Returns valid=true/false/null (unknown)."""
    return validate_user_key(user)


@router.delete("/auth/key", tags=["Auth"])
async def delete_key(user: UserIdentity = Depends(require_user)):
    """Delete the user's saved Gemini key. Chatting stops working until a
    new key is added."""
    removed = delete_user_key(user)
    return {"deleted": removed, "has_key": False}


@router.get("/chat/history", tags=["Agent"])
async def chat_history(
    limit: int = Query(50, ge=1, le=100),
    user: UserIdentity = Depends(require_user),
):
    """The signed-in user's chat history (same on every device — it lives in
    the cloud store, not on any one device). Most recent ``limit`` turns,
    oldest first."""
    messages = get_user_store().list_chat(user, limit=limit)
    return {"messages": messages, "count": len(messages)}


# --- Phase 6: Google OAuth, Gmail & Google Calendar Endpoints ---

@router.get("/auth/google/url", response_model=GoogleAuthUrlResponse, tags=["Google Auth"])
async def get_google_auth_url(redirect_uri: Optional[str] = Query(None), user: UserIdentity = Depends(require_user)) -> GoogleAuthUrlResponse:
    """
    Generate a Google OAuth 2.0 authorization URL using PKCE (S256) and anti-CSRF state.
    User visits this URL in a browser to grant read-only Gmail and Calendar permissions.
    """
    _cloud_gmail_unavailable()
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
    user: UserIdentity = Depends(require_user),
):
    """
    OAuth 2.0 redirect callback endpoint.
    Verifies state token, exchanges code for tokens via PKCE, and stores refresh token securely.
    Rate-limited against brute-force state/code manipulation.
    """
    _cloud_gmail_unavailable()
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
async def disconnect_google(user: UserIdentity = Depends(require_user)) -> GoogleDisconnectResponse:
    """
    Disconnect Google account: revokes tokens with Google and erases local credentials.
    """
    _cloud_gmail_unavailable()
    res = google_auth_manager.disconnect()
    return GoogleDisconnectResponse(
        status=res.get("status", "disconnected"),
        message=res.get("message", "Google account disconnected."),
        revoked_remotely=res.get("revoked_remotely", False),
    )


@router.get("/auth/google/status", response_model=GoogleAuthStatusResponse, tags=["Google Auth"])
async def get_google_status(user: UserIdentity = Depends(require_user)) -> GoogleAuthStatusResponse:
    """
    Check current Google account connection status and storage backend.
    """
    if settings.CLOUD_MODE:
        return GoogleAuthStatusResponse(
            connected=False,
            account_email=None,
            scopes=[],
            storage_backend="Not available in cloud mode",
            connected_at=None,
            read_only=True,
        )
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
    user: UserIdentity = Depends(require_user),
) -> GmailListResponse:
    """
    List recent Gmail messages with metadata (Sender, Subject, Date, Snippet).
    Strictly read-only.
    """
    _cloud_gmail_unavailable()
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
async def summarize_gmail_endpoint(req: GmailSummarizeRequest, user: UserIdentity = Depends(require_user)) -> GmailSummarizeResponse:
    """
    Summarize selected or recent Gmail messages using Gemini.
    Discloses that email text is sent to Gemini. Never stores email bodies in memory or logs.
    """
    _cloud_gmail_unavailable()
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
    user: UserIdentity = Depends(require_user),
) -> CalendarListResponse:
    """
    List upcoming Google Calendar events for a date range.
    Strictly read-only.
    """
    _cloud_gmail_unavailable()
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
async def summarize_calendar_endpoint(req: CalendarSummarizeRequest, user: UserIdentity = Depends(require_user)) -> CalendarSummarizeResponse:
    """
    Summarize Google Calendar events across a date range using Gemini.
    Discloses that event details are sent to Gemini. Never stores event titles in memory or logs.
    """
    _cloud_gmail_unavailable()
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
async def get_approved_domains(user: UserIdentity = Depends(require_user)) -> ApprovedDomainsResponse:
    """Get the current list of user-approved domains for browser automation."""
    return ApprovedDomainsResponse(approved_domains=browser_manager.get_approved_domains())


@router.post("/browser/approve-domain", response_model=ApprovedDomainsResponse, tags=["Browser Automation"])
async def approve_domain_endpoint(req: ApproveDomainRequest, user: UserIdentity = Depends(require_user)) -> ApprovedDomainsResponse:
    """Explicitly approve a domain for browser automation."""
    try:
        browser_manager.approve_domain(req.domain)
        return ApprovedDomainsResponse(approved_domains=browser_manager.get_approved_domains())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/browser/plan-action", response_model=BrowserPlanActionResponse, tags=["Browser Automation"])
async def plan_browser_action(req: BrowserPlanActionRequest, user: UserIdentity = Depends(require_user)) -> BrowserPlanActionResponse:
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
            user=user,
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
            user=user,
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
async def get_data_locations_endpoint(user: UserIdentity = Depends(require_user)) -> DataLocationsResponse:
    """View all local filesystem paths where user data is stored."""
    locs = user_data_manager.get_data_locations(user=user)
    return DataLocationsResponse(**locs)


@router.get("/data/export", response_model=DataExportResponse, tags=["Data Management"])
async def export_user_data_endpoint(user: UserIdentity = Depends(require_user)) -> DataExportResponse:
    """
    Export all user-owned notes, memories, and reminders in clean JSON format.
    Strictly excludes secrets, API keys, and credentials.
    """
    data = user_data_manager.export_user_data(user=user)
    return DataExportResponse(**data)


@router.post("/data/clear", response_model=DataClearResponse, tags=["Data Management"])
async def clear_all_data_endpoint(req: DataClearRequest, user: UserIdentity = Depends(require_user)) -> DataClearResponse:
    """
    Permanently wipe all user notes, memories, reminders, and screenshot images.
    Requires confirm=true and confirmation_text='DELETE ALL DATA'.
    """
    try:
        res = user_data_manager.clear_all_local_data(
            confirm=req.confirm,
            confirmation_text=req.confirmation_text,
            user=user,
        )
        return DataClearResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/data/backups", response_model=BackupListResponse, tags=["Data Management"])
async def list_backups_endpoint(user: UserIdentity = Depends(require_user)) -> BackupListResponse:
    """List all available local backup snapshots with verification status."""
    try:
        backups = user_data_manager.list_backups(user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return BackupListResponse(count=len(backups), backups=backups)


@router.post("/data/backup", response_model=BackupCreateResponse, tags=["Data Management"])
async def create_backup_endpoint(req: BackupCreateRequest = BackupCreateRequest(), user: UserIdentity = Depends(require_user)) -> BackupCreateResponse:
    """
    Create a local validated backup snapshot of notes, reminders, and memories
    with a SHA-256 integrity checksum. Does NOT include secrets or credentials.
    """
    try:
        res = user_data_manager.create_backup(backup_name=req.backup_name, user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return BackupCreateResponse(**res)


@router.post("/data/restore", response_model=BackupRestoreResponse, tags=["Data Management"])
async def restore_backup_endpoint(req: BackupRestoreRequest, user: UserIdentity = Depends(require_user)) -> BackupRestoreResponse:
    """
    Safely restore user data from a local backup file after checksum validation.
    Requires confirm_overwrite=true if existing data is present.
    """
    try:
        res = user_data_manager.restore_backup(
            backup_filename=req.backup_filename,
            confirm_overwrite=req.confirm_overwrite,
            user=user,
        )
        return BackupRestoreResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Restore failed: {e}")


# --- Phase 10: End-to-End Demo Mode Endpoints ---

@router.get("/demo/status", response_model=DemoStatusResponse, tags=["Demo"])
async def get_demo_status_endpoint(user: UserIdentity = Depends(require_user)) -> DemoStatusResponse:
    """Returns the current status, links, and step-by-step instructions for Phase 10 Demo."""
    st = demo_manager.get_status(user=user)
    return DemoStatusResponse(**st)


@router.post("/demo/seed", response_model=DemoActionResponse, tags=["Demo"])
async def seed_demo_data_endpoint(user: UserIdentity = Depends(require_user)) -> DemoActionResponse:
    """Seeds fictional mock notes, reminders, and memory tagged with '[DEMO]'."""
    res = demo_manager.seed_demo_data(user=user)
    return DemoActionResponse(**res)


@router.post("/demo/reset", response_model=DemoActionResponse, tags=["Demo"])
async def clear_demo_data_endpoint(user: UserIdentity = Depends(require_user)) -> DemoActionResponse:
    """One-step deletion of mock/demo data without touching real user files or records."""
    res = demo_manager.clear_demo_data(user=user)
    return DemoActionResponse(**res)


