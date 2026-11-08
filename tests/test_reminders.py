from unittest.mock import MagicMock
import pytest

from app.core.confirmation import confirmation_manager
from app.tools.reminders_tools import (
    create_reminder,
    list_reminders,
    complete_reminder,
    delete_reminder,
    reminders_storage,
)


def test_create_reminder_success():
    result = create_reminder(
        title="Dentist Appointment",
        due_time="Tomorrow at 3:00 PM",
        notes="Bring medical card",
    )
    assert result.success is True
    assert result.output["reminder"]["title"] == "Dentist Appointment"
    assert result.output["reminder"]["due_time"] == "Tomorrow at 3:00 PM"
    assert result.output["reminder"]["completed"] is False
    assert "stored locally" in result.output["notice"]


def test_create_reminder_validation_errors():
    assert create_reminder(title="", due_time="Tomorrow").success is False
    assert create_reminder(title="Test", due_time="").success is False


def test_list_and_complete_reminders():
    r1 = create_reminder(title="Task 1", due_time="Today").output["reminder"]
    r2 = create_reminder(title="Task 2", due_time="Tomorrow").output["reminder"]

    # Active list
    list_res = list_reminders(include_completed=False)
    assert list_res.success is True
    assert list_res.output["count"] == 2

    # Complete Task 1
    comp_res = complete_reminder(r1["id"])
    assert comp_res.success is True
    assert comp_res.output["reminder"]["completed"] is True

    # Active list should now show 1
    active_res = list_reminders(include_completed=False)
    assert active_res.output["count"] == 1
    assert active_res.output["reminders"][0]["id"] == r2["id"]

    # List including completed should show 2
    all_res = list_reminders(include_completed=True)
    assert all_res.output["count"] == 2


def test_delete_reminder_requires_confirmation():
    r = create_reminder(title="To be deleted", due_time="Soon").output["reminder"]
    rem_id = r["id"]

    # Missing confirmation_id
    del_res1 = delete_reminder(rem_id)
    assert del_res1.success is False
    assert "Confirmation required" in del_res1.error
    assert del_res1.output["requires_confirmation"] is True
    conf_id = del_res1.output["confirmation_id"]

    # Confirm action
    confirmation_manager.confirm_action(conf_id)

    # Perform confirmed deletion
    del_res2 = delete_reminder(rem_id, confirmation_id=conf_id)
    assert del_res2.success is True
    assert "successfully deleted" in del_res2.output["message"]

    # Verify gone
    assert reminders_storage.get_by_id(rem_id) is None


def test_reminders_api_endpoints(client):
    # 1. Create reminder via API
    res = client.post(
        "/api/reminders",
        json={
            "title": "Study FastAPI",
            "due_time": "Friday at 5 PM",
            "notes": "Chapter 4",
        },
    )
    assert res.status_code == 201
    data = res.json()
    rem_id = data["id"]
    assert data["title"] == "Study FastAPI"

    # 2. List reminders via API
    list_res = client.get("/api/reminders")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Mark complete via API
    comp_res = client.patch(f"/api/reminders/{rem_id}/complete")
    assert comp_res.status_code == 200
    assert comp_res.json()["completed"] is True

    # 4. Request delete via API (returns confirmation requirement)
    del_req = client.delete(f"/api/reminders/{rem_id}")
    assert del_req.status_code == 200
    del_data = del_req.json()
    assert del_data["requires_confirmation"] is True
    conf_id = del_data["confirmation_id"]

    # 5. Confirm deletion via confirm API
    confirm_res = client.post("/api/confirm", json={"confirmation_id": conf_id, "approve": True})
    assert confirm_res.status_code == 200
    assert confirm_res.json()["success"] is True
