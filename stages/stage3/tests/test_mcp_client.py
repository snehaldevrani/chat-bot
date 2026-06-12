from unittest.mock import patch, AsyncMock


def test_call_mcp_write_returns_error_when_server_unreachable():
    """Returns an ERROR string when the MCP server is not running."""
    from src.mcp_server.client import call_mcp_write

    result = call_mcp_write(
        reservation_id="rid-fail-001",
        name="Bob", surname="Jones", car_number="BJ02ZZ",
        start_datetime="2026-06-16 10:00", end_datetime="2026-06-16 14:00",
        space_type="vip",
        approval_time="2026-06-16 09:50:00",
    )
    assert result.startswith("ERROR")


def test_call_mcp_write_auto_generates_approval_time():
    """approval_time is filled when None is passed."""
    from src.mcp_server import client as client_mod

    async def fake_write_tool(**kwargs):
        return kwargs.get("approval_time", "")

    with patch.object(client_mod, "_call_write_tool", new=fake_write_tool):
        result = client_mod.call_mcp_write(
            reservation_id="rid-001",
            name="Alice", surname="Brown", car_number="AB01XY",
            start_datetime="2026-06-15 09:00", end_datetime="2026-06-15 17:00",
            space_type="regular",
            approval_time=None,
        )

    assert result is not None
    assert len(result) > 0


def test_call_mcp_write_passes_explicit_approval_time():
    """Explicit approval_time is forwarded to the underlying async call."""
    from src.mcp_server import client as client_mod

    captured = {}

    async def fake_write_tool(**kwargs):
        captured.update(kwargs)
        return "OK"

    with patch.object(client_mod, "_call_write_tool", new=fake_write_tool):
        client_mod.call_mcp_write(
            reservation_id="rid-002",
            name="Carol", surname="White", car_number="CW03AA",
            start_datetime="2026-06-17 08:00", end_datetime="2026-06-17 20:00",
            space_type="ev_charging",
            approval_time="2026-06-17 07:55:00",
        )

    assert captured.get("approval_time") == "2026-06-17 07:55:00"
