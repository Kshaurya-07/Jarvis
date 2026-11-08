import time
import pytest

from app.core.confirmation import ConfirmationManager


def test_confirmation_lifecycle():
    mgr = ConfirmationManager(timeout_seconds=60)

    # 1. Create action
    action = mgr.create_pending_action(
        tool_name="open_application",
        arguments={"app_name": "notepad"},
        description="Launch notepad",
    )
    conf_id = action.confirmation_id
    assert conf_id.startswith("conf_")

    # 2. Before approval: consumption should fail
    assert mgr.validate_and_consume(conf_id, "open_application", {"app_name": "notepad"}) is False

    # 3. Approve action
    approved = mgr.confirm_action(conf_id)
    assert approved is not None
    assert approved.confirmed is True

    # 4. Consume with matching args
    assert mgr.validate_and_consume(conf_id, "open_application", {"app_name": "notepad"}) is True

    # 5. Double consumption must fail (single-use)
    assert mgr.validate_and_consume(conf_id, "open_application", {"app_name": "notepad"}) is False


def test_confirmation_rejects_argument_tampering():
    mgr = ConfirmationManager(timeout_seconds=60)
    action = mgr.create_pending_action(
        tool_name="open_application",
        arguments={"app_name": "notepad"},
        description="Launch notepad",
    )
    mgr.confirm_action(action.confirmation_id)

    # Attempt to consume with altered arguments (tampering)
    assert mgr.validate_and_consume(
        action.confirmation_id,
        "open_application",
        {"app_name": "cmd"},
    ) is False


def test_confirmation_denial():
    mgr = ConfirmationManager(timeout_seconds=60)
    action = mgr.create_pending_action(
        tool_name="capture_screenshot",
        arguments={},
        description="Take screenshot",
    )
    conf_id = action.confirmation_id

    assert mgr.deny_action(conf_id) is True
    assert mgr.get_action(conf_id) is None


def test_confirmation_expiration():
    # 0 second timeout for instant expiration
    mgr = ConfirmationManager(timeout_seconds=0)
    action = mgr.create_pending_action(
        tool_name="open_application",
        arguments={"app_name": "paint"},
        description="Launch paint",
    )
    time.sleep(0.01)
    mgr.cleanup_expired()

    assert mgr.get_action(action.confirmation_id) is None
