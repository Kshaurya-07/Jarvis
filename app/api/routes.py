import sys
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

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
)
from app.core.config import settings
from app.core.confirmation import confirmation_manager
from app.core.logger import action_logger, ActionLogEntry
from app.services.agent_service import agent_service
from app.services.extension_service import extension_service
from app.tools.registry import tool_registry
from app.tools.reminders_tools import reminders_storage, delete_reminder
from app.tools.memory_tools import memory_storage, detect_sensitive_data
from app.tools.briefing_tools import build_daily_briefing

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """System health-check verifying server readiness, storage paths, and active tools."""
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
        workspace_directory=str(settings.WORKSPACE_DIR),
        notes_directory=str(settings.NOTES_DIR),
        screenshots_directory=str(settings.SCREENSHOTS_DIR),
        reminders_count=rem_count,
        memories_count=mem_count,
        memory_enabled=settings.MEMORY_ENABLED,
        active_tools=tools,
    )


@router.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
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
async def list_tools() -> List[ToolInfo]:
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
async def get_recent_actions(limit: int = 50) -> List[ActionLogEntry]:
    """Returns recent tool actions from the in-memory audit log."""
    safe_limit = max(1, min(limit, 100))
    return action_logger.get_recent_actions(limit=safe_limit)


# --- Confirmation Management Endpoints ---

@router.get("/confirm/pending", response_model=List[PendingActionInfo], tags=["Confirmation"])
async def get_pending_confirmations() -> List[PendingActionInfo]:
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
async def confirm_action(req: ConfirmationRequest) -> ConfirmationResponse:
    """
    Explicitly approve or deny a pending action requiring confirmation.
    If approved, executes the tool safely and returns the output.
    """
    if not req.approve:
        denied = confirmation_manager.deny_action(req.confirmation_id)
        if denied:
            return ConfirmationResponse(
                success=True,
                message=f"Action '{req.confirmation_id}' has been denied and cancelled.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pending action '{req.confirmation_id}' not found or already expired.",
            )

    # Approve
    action = confirmation_manager.confirm_action(req.confirmation_id)
    if not action:
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
async def read_page_endpoint(req: PageReadRequest) -> PageReadResponse:
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
async def get_reminders(include_completed: bool = False) -> List[ReminderResponse]:
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
async def create_reminder_endpoint(req: ReminderCreateRequest) -> ReminderResponse:
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
async def mark_reminder_completed(reminder_id: str) -> ReminderResponse:
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
async def get_memories() -> List[MemoryResponse]:
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
async def add_or_update_memory(req: MemoryCreateRequest) -> MemoryResponse:
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
async def delete_memory_by_key(key: str):
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
    confirm: bool = Query(False, description="Set confirm=true to clear all memories.")
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
async def get_memory_status() -> MemoryStatusResponse:
    """Get memory system status and item count."""
    return MemoryStatusResponse(
        enabled=settings.MEMORY_ENABLED,
        count=len(memory_storage.list_all()),
    )


@router.post("/memories/toggle", response_model=MemoryStatusResponse, tags=["Memory"])
async def toggle_memory(req: MemoryToggleRequest) -> MemoryStatusResponse:
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
