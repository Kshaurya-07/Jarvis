from typing import List
from fastapi import APIRouter, HTTPException, status

from app import __version__
from app.api.schemas import ChatRequest, ChatResponse, HealthResponse, ToolInfo, ToolExecutionInfo
from app.core.config import settings
from app.core.logger import action_logger, ActionLogEntry
from app.services.agent_service import agent_service
from app.tools.registry import tool_registry

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """System health-check verifying server readiness, storage paths, and active tools."""
    tools = [t.name for t in tool_registry.get_all_tools()]
    return HealthResponse(
        status="ok",
        version=__version__,
        gemini_configured=agent_service.is_configured(),
        workspace_directory=str(settings.WORKSPACE_DIR),
        notes_directory=str(settings.NOTES_DIR),
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
    """Returns all currently active and approved Phase 1 tools."""
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
