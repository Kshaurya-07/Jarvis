
from app.core.logger import action_logger
from app.tools.registry import tool_registry


def test_registry_executes_registered_tool():
    result = tool_registry.execute_tool(
        name="create_note",
        arguments={"title": "Registry Test", "content": "Testing tool execution."},
    )
    assert result.success is True
    assert result.output["title"] == "Registry Test"


def test_registry_rejects_unknown_tool():
    result = tool_registry.execute_tool(
        name="execute_system_command",
        arguments={"cmd": "whoami"},
    )
    assert result.success is False
    assert "Unknown tool 'execute_system_command'" in result.error


def test_registry_validates_arguments():
    # Missing required argument 'title' for create_note
    result = tool_registry.execute_tool(
        name="create_note",
        arguments={"content": "missing title"},
    )
    assert result.success is False
    assert "Argument 'title' is required" in result.error


def test_registry_audit_log_recorded():
    initial_count = len(action_logger.get_recent_actions())
    tool_registry.execute_tool(
        name="list_files",
        arguments={"subfolder": ""},
    )
    actions = action_logger.get_recent_actions()
    assert len(actions) >= initial_count + 1
    last_action = actions[-1]
    assert last_action.tool_name == "list_files"
    assert last_action.status == "success"
    assert last_action.execution_time_ms is not None
