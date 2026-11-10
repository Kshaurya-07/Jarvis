
from app.core.config import settings
from app.tools.memory_tools import (
    remember_item,
    forget_item,
    list_memories,
    detect_sensitive_data,
    memory_storage,
)


def test_remember_and_list_memories():
    res1 = remember_item(key="favorite_editor", content="Visual Studio Code with Python extension")
    assert res1.success is True
    assert res1.output["memory"]["key"] == "favorite_editor"

    res2 = remember_item(key="study_goal", content="Master FastAPI and Gemini SDK")
    assert res2.success is True

    mem_list = list_memories()
    assert mem_list.success is True
    assert mem_list.output["count"] == 2
    keys = [m["key"] for m in mem_list.output["memories"]]
    assert "favorite_editor" in keys
    assert "study_goal" in keys


def test_forget_memory():
    remember_item(key="temp_fact", content="Temporary information to remove.")
    assert memory_storage.get("temp_fact") is not None

    res = forget_item(key="temp_fact")
    assert res.success is True
    assert "Successfully forgot" in res.output["message"]
    assert memory_storage.get("temp_fact") is None


def test_forget_nonexistent_memory():
    res = forget_item(key="nonexistent_key_1234")
    assert res.success is False
    assert "No memory found" in res.error


def test_sensitive_data_detection():
    # Passwords
    assert detect_sensitive_data("my password is: SuperSecret99!") is not None
    assert detect_sensitive_data("pwd=my_secret_pass") is not None

    # API Keys & Tokens
    assert detect_sensitive_data("api_key = 'abcdef1234567890abcdef'") is not None
    assert detect_sensitive_data("api_key = 'TEST-FAKE-KEY-1234567890'") is not None
    assert detect_sensitive_data("Bearer TEST-FAKE-TOKEN-123456789012345") is not None

    # Credit cards
    assert detect_sensitive_data("card number 4111 2222 3333 4444") is not None

    # Safe text
    assert detect_sensitive_data("I enjoy learning Python and algorithms.") is None


def test_remember_rejects_sensitive_data():
    res1 = remember_item(key="site_login", content="password: my_secret_password_123")
    assert res1.success is False
    assert "Privacy refusal" in res1.error

    res2 = remember_item(key="cloud_key", content="api_key = 'TEST-FAKE-KEY-1234567890'")
    assert res2.success is False
    assert "Privacy refusal" in res2.error


def test_memory_disabled_setting(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_ENABLED", False)

    res = remember_item(key="preference", content="Dark mode")
    assert res.success is False
    assert "currently disabled" in res.error

    # list_memories reports disabled status
    list_res = list_memories()
    assert list_res.success is True
    assert list_res.output["enabled"] is False


def test_memory_api_endpoints(client):
    # 1. Store memory
    res = client.post(
        "/api/memories",
        json={"key": "preferred_language", "content": "Python"},
    )
    assert res.status_code == 201
    assert res.json()["key"] == "preferred_language"

    # 2. Refuses sensitive credential via API
    res_sensitive = client.post(
        "/api/memories",
        json={"key": "api_secret", "content": "api_key = '1234567890abcdef1234567890'"},
    )
    assert res_sensitive.status_code == 400
    assert "Privacy refusal" in res_sensitive.json()["detail"]

    # 3. List memories via API
    res_list = client.get("/api/memories")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # 4. Delete single memory
    res_del = client.delete("/api/memories/preferred_language")
    assert res_del.status_code == 200

    # 5. Toggle memory setting
    res_toggle = client.post("/api/memories/toggle", json={"enabled": False})
    assert res_toggle.status_code == 200
    assert res_toggle.json()["enabled"] is False

    # 6. Clear all memories (requires confirm=true)
    res_clear_no_confirm = client.delete("/api/memories")
    assert res_clear_no_confirm.status_code == 400

    res_clear_confirmed = client.delete("/api/memories?confirm=true")
    assert res_clear_confirmed.status_code == 200
    assert "Cleared all memories" in res_clear_confirmed.json()["message"]
