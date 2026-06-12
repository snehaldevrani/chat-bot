import pytest
import os
import uuid
import tempfile
from unittest.mock import patch


# ---------- Tool logic tests (direct calls, no MCP protocol) ----------

def test_write_reservation_invalid_token():
    from src.mcp_server.server import write_confirmed_reservation
    result = write_confirmed_reservation(
        token="wrong-token",
        reservation_id=str(uuid.uuid4()),
        name="John", surname="Doe", car_number="ABC-123",
        start_datetime="2026-06-10 09:00", end_datetime="2026-06-10 18:00",
        approval_time="2026-06-10 08:00:00", space_type="regular",
    )
    assert "ERROR" in result
    assert "Unauthorized" in result


def test_write_reservation_creates_file():
    from src.mcp_server.server import write_confirmed_reservation
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with patch("src.mcp_server.server.RESERVATIONS_FILE", tmp_path), \
             patch("src.mcp_server.server._LOCK_FILE", tmp_path + ".lock"), \
             patch("src.mcp_server.server.MCP_SECRET_TOKEN", "test-token"):
            rid = str(uuid.uuid4())
            result = write_confirmed_reservation(
                token="test-token",
                reservation_id=rid,
                name="Alice", surname="Smith", car_number="XYZ-999",
                start_datetime="2026-06-11 10:00", end_datetime="2026-06-11 16:00",
                approval_time="2026-06-11 09:55:00", space_type="vip",
            )
        assert "OK" in result
        content = open(tmp_path, encoding="utf-8").read()
        assert "Alice Smith" in content
        assert "XYZ-999" in content
        assert "Vip" in content
    finally:
        os.unlink(tmp_path)
        lock = tmp_path + ".lock"
        if os.path.exists(lock):
            os.unlink(lock)


def test_write_reservation_correct_format():
    from src.mcp_server.server import write_confirmed_reservation
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with patch("src.mcp_server.server.RESERVATIONS_FILE", tmp_path), \
             patch("src.mcp_server.server._LOCK_FILE", tmp_path + ".lock"), \
             patch("src.mcp_server.server.MCP_SECRET_TOKEN", "test-token"):
            rid = str(uuid.uuid4())
            write_confirmed_reservation(
                token="test-token",
                reservation_id=rid,
                name="Bob", surname="Jones", car_number="DEF-456",
                start_datetime="2026-06-12 08:00", end_datetime="2026-06-12 12:00",
                approval_time="2026-06-12 07:50:00", space_type="regular",
            )
        content = open(tmp_path, encoding="utf-8").read()
        data_lines = [l for l in content.splitlines() if not l.startswith("#") and l.strip()]
        assert len(data_lines) == 1
        parts = data_lines[0].split(" | ")
        assert len(parts) == 6
        assert parts[0] == "Bob Jones"
        assert parts[1] == "DEF-456"
        assert "2026-06-12 08:00 to 2026-06-12 12:00" in parts[2]
        assert parts[3] == "2026-06-12 07:50:00"
        assert parts[4] == "Regular"
    finally:
        os.unlink(tmp_path)
        lock = tmp_path + ".lock"
        if os.path.exists(lock):
            os.unlink(lock)


def test_write_reservation_idempotent():
    from src.mcp_server.server import write_confirmed_reservation
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        rid = str(uuid.uuid4())
        with patch("src.mcp_server.server.RESERVATIONS_FILE", tmp_path), \
             patch("src.mcp_server.server._LOCK_FILE", tmp_path + ".lock"), \
             patch("src.mcp_server.server.MCP_SECRET_TOKEN", "test-token"):
            write_confirmed_reservation(
                token="test-token", reservation_id=rid,
                name="Sara", surname="Lee", car_number="GHI-789",
                start_datetime="2026-06-13 09:00", end_datetime="2026-06-13 17:00",
                approval_time="2026-06-13 08:45:00", space_type="ev_charging",
            )
            result2 = write_confirmed_reservation(
                token="test-token", reservation_id=rid,
                name="Sara", surname="Lee", car_number="GHI-789",
                start_datetime="2026-06-13 09:00", end_datetime="2026-06-13 17:00",
                approval_time="2026-06-13 08:45:00", space_type="ev_charging",
            )
        assert "SKIPPED" in result2
        content = open(tmp_path, encoding="utf-8").read()
        data_lines = [l for l in content.splitlines() if not l.startswith("#") and l.strip()]
        assert len(data_lines) == 1
    finally:
        os.unlink(tmp_path)
        lock = tmp_path + ".lock"
        if os.path.exists(lock):
            os.unlink(lock)


def test_list_reservations_invalid_token():
    from src.mcp_server.server import list_confirmed_reservations
    result = list_confirmed_reservations(token="bad-token")
    assert "ERROR" in result


def test_list_reservations_empty_file():
    from src.mcp_server.server import list_confirmed_reservations
    with patch("src.mcp_server.server.RESERVATIONS_FILE", "/nonexistent/path/reservations.txt"), \
         patch("src.mcp_server.server.MCP_SECRET_TOKEN", "test-token"):
        result = list_confirmed_reservations(token="test-token")
    assert "No confirmed" in result


def test_write_multiple_reservations():
    from src.mcp_server.server import write_confirmed_reservation
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with patch("src.mcp_server.server.RESERVATIONS_FILE", tmp_path), \
             patch("src.mcp_server.server._LOCK_FILE", tmp_path + ".lock"), \
             patch("src.mcp_server.server.MCP_SECRET_TOKEN", "test-token"):
            for i in range(3):
                write_confirmed_reservation(
                    token="test-token", reservation_id=str(uuid.uuid4()),
                    name=f"User{i}", surname="Test", car_number=f"CAR-00{i}",
                    start_datetime="2026-06-14 09:00", end_datetime="2026-06-14 17:00",
                    approval_time="2026-06-14 08:00:00", space_type="regular",
                )
        content = open(tmp_path, encoding="utf-8").read()
        data_lines = [l for l in content.splitlines() if not l.startswith("#") and l.strip()]
        assert len(data_lines) == 3
    finally:
        os.unlink(tmp_path)
        lock = tmp_path + ".lock"
        if os.path.exists(lock):
            os.unlink(lock)


# ---------- MCP server instantiation test ----------

def test_mcp_server_has_tools():
    from src.mcp_server.server import mcp
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    assert "write_confirmed_reservation" in tool_names
    assert "list_confirmed_reservations" in tool_names
