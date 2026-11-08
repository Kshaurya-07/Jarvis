import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logger import app_logger
from app.tools.registry import tool_registry


SYSTEM_INSTRUCTION = """
You are Jarvis, a secure personal AI assistant.
You assist the user by executing approved tools when requested.
Current Phase 1 available capabilities:
- list_files: list files in the configured workspace folder.
- read_text_file: read a text file inside the workspace folder.
- create_note: save a note in the notes folder.
- search_notes: search saved notes by keyword.

Safety & Honesty rules:
1. Only call tools that are explicitly registered.
2. If asked to perform actions not supported yet (e.g., executing arbitrary code, web browsing, voice, email, system settings), politely explain that this feature is planned for a future phase and not yet implemented.
3. Be concise, direct, and polite.
""".strip()


class ToolExecutionRecord(BaseModel):
    """Summary of a tool call executed during an agent interaction."""
    tool_name: str
    arguments: Dict[str, Any]
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None


class AgentResponse(BaseModel):
    """Response returned from the agent to the API caller."""
    message: str
    tools_executed: List[ToolExecutionRecord] = Field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class AgentService:
    """Orchestrates Gemini API interactions, tool dispatching, and conversation turns."""

    def __init__(self):
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Lazily initialize and return the official Gemini client."""
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if not api_key or api_key.strip() in ("", "your_gemini_api_key_here"):
            raise ValueError(
                "Gemini API key is not configured. Please set the GEMINI_API_KEY "
                "environment variable or define it in your .env file."
            )
        return genai.Client(api_key=api_key.strip())

    def is_configured(self) -> bool:
        """Check if a valid Gemini API key is configured."""
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        return bool(api_key and api_key.strip() not in ("", "your_gemini_api_key_here"))

    async def chat(self, user_message: str) -> AgentResponse:
        """
        Process a user message through Gemini with tool calling.
        Executes approved tools and returns the synthesized assistant response.
        """
        if not user_message or not user_message.strip():
            return AgentResponse(
                message="Message cannot be empty.",
                success=False,
                error="Empty input received.",
            )

        if len(user_message) > settings.MAX_REQUEST_LENGTH:
            return AgentResponse(
                message=f"Message exceeds maximum allowed length of {settings.MAX_REQUEST_LENGTH} characters.",
                success=False,
                error="Message length limit exceeded.",
            )

        try:
            client = self._get_client()
        except ValueError as e:
            return AgentResponse(
                message=(
                    "Jarvis core is running, but Gemini API is not yet configured. "
                    "Please set your GEMINI_API_KEY in the .env file to enable AI reasoning and tool calling."
                ),
                success=False,
                error=str(e),
            )

        # Prepare Gemini tool configuration
        gemini_tools = [
            types.Tool(function_declarations=tool_registry.get_gemini_tool_declarations())
        ]

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=gemini_tools,
            temperature=0.2,  # Low temperature for tool reliability
        )

        contents: List[types.Content] = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message.strip())],
            )
        ]

        executed_tools: List[ToolExecutionRecord] = []
        max_turns = 5  # Prevent runaway tool call loops
        turn = 0

        try:
            while turn < max_turns:
                turn += 1

                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=contents,
                    config=config,
                )

                # Check if Gemini decided to invoke any function calls
                function_calls = response.function_calls

                if not function_calls:
                    # Model provided final text response
                    final_text = response.text or ""
                    return AgentResponse(
                        message=final_text,
                        tools_executed=executed_tools,
                        success=True,
                    )

                # Append model's turn to conversation history
                if response.candidates and response.candidates[0].content:
                    contents.append(response.candidates[0].content)

                # Execute requested tools
                tool_response_parts: List[types.Part] = []

                for fc in function_calls:
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    # Execute tool via registry (performs validation & logging)
                    result = tool_registry.execute_tool(tool_name, tool_args)

                    executed_tools.append(
                        ToolExecutionRecord(
                            tool_name=tool_name,
                            arguments=tool_args,
                            success=result.success,
                            output=result.output,
                            error=result.error,
                        )
                    )

                    # Prepare function response part for Gemini
                    tool_response_dict = result.to_dict()
                    part = types.Part.from_function_response(
                        name=tool_name,
                        response={"result": tool_response_dict},
                    )
                    tool_response_parts.append(part)

                # Append tool results as a single tool content turn
                contents.append(
                    types.Content(role="tool", parts=tool_response_parts)
                )

            # If loop limit reached
            return AgentResponse(
                message="Completed maximum tool execution turns.",
                tools_executed=executed_tools,
                success=True,
            )

        except Exception as e:
            app_logger.error("Gemini API call failed: %s", str(e), exc_info=True)
            return AgentResponse(
                message=f"Encountered an error while communicating with Gemini API: {str(e)}",
                tools_executed=executed_tools,
                success=False,
                error=str(e),
            )


# Global instance
agent_service = AgentService()
