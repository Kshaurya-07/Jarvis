from unittest.mock import AsyncMock, patch

from app.services.agent_service import AgentResponse, ToolExecutionRecord


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "active_tools" in data
    assert "list_files" in data["active_tools"]
    assert "create_note" in data["active_tools"]


def test_api_tools_endpoint(client):
    response = client.get("/api/tools")
    assert response.status_code == 200
    tools = response.json()
    tool_names = [t["name"] for t in tools]
    assert "list_files" in tool_names
    assert "read_text_file" in tool_names
    assert "create_note" in tool_names
    assert "search_notes" in tool_names


def test_chat_empty_message_validation(client):
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422  # Pydantic validation error for min_length=1


def test_chat_exceeds_length_validation(client):
    response = client.post("/api/chat", json={"message": "A" * 600})
    # Conftest sets MAX_REQUEST_LENGTH to 500
    assert response.status_code == 400
    assert "exceeds maximum length" in response.json()["detail"]


def test_chat_without_api_key(client):
    # With no key set, chat should return a clear, user-friendly response rather than crashing
    response = client.post("/api/chat", json={"message": "What files do I have?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "GEMINI_API_KEY" in data["reply"]


def test_chat_with_mocked_agent(client):
    mock_agent_response = AgentResponse(
        message="I listed your files. Found 1 file.",
        tools_executed=[
            ToolExecutionRecord(
                tool_name="list_files",
                arguments={"subfolder": ""},
                success=True,
                output={"count": 1, "items": [{"name": "test.txt", "type": "file"}]},
            )
        ],
        success=True,
    )

    with patch("app.api.routes.agent_service.chat", new=AsyncMock(return_value=mock_agent_response)):
        response = client.post("/api/chat", json={"message": "List my files please."})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Found 1 file" in data["reply"]
        assert len(data["tools_executed"]) == 1
        assert data["tools_executed"][0]["tool_name"] == "list_files"


def test_actions_audit_endpoint(client):
    response = client.get("/api/actions")
    assert response.status_code == 200
    actions = response.json()
    assert isinstance(actions, list)
