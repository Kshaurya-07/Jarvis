import sys
from unittest.mock import MagicMock, patch
import pytest

from app.tools.system_status_tools import (
    get_battery_status,
    get_storage_status,
    get_memory_status,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only system-status tool")
def test_battery_status_desktop_no_battery():
    with patch("psutil.sensors_battery", return_value=None):
        result = get_battery_status()
        assert result.success is True
        assert result.output["battery_present"] is False
        assert "No battery detected" in result.output["summary"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only system-status tool")
def test_battery_status_laptop_charging():
    mock_battery = MagicMock()
    mock_battery.percent = 85.5
    mock_battery.power_plugged = True
    mock_battery.secsleft = -2

    with patch("psutil.sensors_battery", return_value=mock_battery):
        result = get_battery_status()
        assert result.success is True
        assert result.output["battery_present"] is True
        assert result.output["percent"] == 85.5
        assert result.output["power_plugged"] is True
        assert "plugged in" in result.output["summary"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only system-status tool")
def test_battery_status_laptop_discharging():
    mock_battery = MagicMock()
    mock_battery.percent = 45.0
    mock_battery.power_plugged = False
    mock_battery.secsleft = 5400  # 1 hour 30 min

    with patch("psutil.sensors_battery", return_value=mock_battery):
        result = get_battery_status()
        assert result.success is True
        assert result.output["percent"] == 45.0
        assert result.output["power_plugged"] is False
        assert "1h 30m" in result.output["time_remaining"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only system-status tool")
def test_storage_status_valid_drive():
    mock_usage = MagicMock()
    mock_usage.total = 500 * (1024 ** 3)
    mock_usage.used = 200 * (1024 ** 3)
    mock_usage.free = 300 * (1024 ** 3)
    mock_usage.percent = 40.0

    with patch("psutil.disk_usage", return_value=mock_usage):
        result = get_storage_status(drive="C:")
        assert result.success is True
        assert result.output["drive"] == "C:"
        assert result.output["total_gb"] == 500.0
        assert result.output["free_gb"] == 300.0
        assert result.output["percent_used"] == 40.0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only system-status tool")
def test_storage_status_invalid_drive_format():
    result = get_storage_status(drive="invalid_drive")
    assert result.success is False
    assert "Invalid drive specification" in result.error


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only system-status tool")
def test_storage_status_nonexistent_drive():
    with patch("psutil.disk_usage", side_effect=FileNotFoundError("Drive not found")):
        result = get_storage_status(drive="Z:")
        assert result.success is False
        assert "was not found" in result.error


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only system-status tool")
def test_memory_status_success():
    mock_mem = MagicMock()
    mock_mem.total = 16 * (1024 ** 3)
    mock_mem.available = 8 * (1024 ** 3)
    mock_mem.used = 8 * (1024 ** 3)
    mock_mem.percent = 50.0

    with patch("psutil.virtual_memory", return_value=mock_mem):
        result = get_memory_status()
        assert result.success is True
        assert result.output["total_gb"] == 16.0
        assert result.output["available_gb"] == 8.0
        assert result.output["percent_used"] == 50.0


def test_system_status_unsupported_platform():
    with patch("sys.platform", "darwin"):
        assert get_battery_status().success is False
        assert get_storage_status().success is False
        assert get_memory_status().success is False
