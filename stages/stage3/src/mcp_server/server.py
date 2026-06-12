import hmac
import threading
from pathlib import Path

import filelock
from mcp.server.fastmcp import FastMCP

from src.config import MCP_SECRET_TOKEN, MCP_SERVER_PORT, RESERVATIONS_FILE

mcp = FastMCP(
    "CityPark Reservation Writer",
    host="127.0.0.1",
    port=MCP_SERVER_PORT,
)

_LOCK_FILE = RESERVATIONS_FILE + ".lock"
_HEADER = (
    "# CityPark Premium Parking - Confirmed Reservations Log\n"
    "# Format: Name | Car Number | Reservation Period | Approval Time\n"
)


def _ensure_file() -> None:
    path = Path(RESERVATIONS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_HEADER, encoding="utf-8")


def _already_written(line: str) -> bool:
    try:
        content = Path(RESERVATIONS_FILE).read_text(encoding="utf-8")
        return line.strip() in content
    except FileNotFoundError:
        return False


@mcp.tool()
def write_confirmed_reservation(
    token: str,
    reservation_id: str,
    name: str,
    surname: str,
    car_number: str,
    start_datetime: str,
    end_datetime: str,
    approval_time: str,
    space_type: str,
) -> str:
    """
    Write an approved reservation to the Stage 3 text log.

    The `space_type` and `reservation_id` inputs are accepted for integration
    context, but the assignment-required file entry stays four columns:
    Name | Car Number | Reservation Period | Approval Time.
    """
    if not hmac.compare_digest(token, MCP_SECRET_TOKEN):
        return "ERROR: Unauthorized. Invalid token."

    _ensure_file()

    full_name = f"{name} {surname}"
    period = f"{start_datetime} to {end_datetime}"
    short_id = reservation_id[:8].upper()
    line = f"{full_name} | {car_number} | {period} | {approval_time}\n"

    if _already_written(line):
        return f"SKIPPED: Reservation {short_id} already logged."

    lock = filelock.FileLock(_LOCK_FILE, timeout=5)
    with lock:
        with open(RESERVATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(line)

    print(f"[MCPServer] Written reservation {short_id} to {RESERVATIONS_FILE}")
    return f"OK: Reservation {short_id} written successfully."


@mcp.tool()
def list_confirmed_reservations(token: str) -> str:
    """Return all confirmed reservations from the log file."""
    if not hmac.compare_digest(token, MCP_SECRET_TOKEN):
        return "ERROR: Unauthorized. Invalid token."
    try:
        content = Path(RESERVATIONS_FILE).read_text(encoding="utf-8")
        lines = [line for line in content.splitlines() if line and not line.startswith("#")]
        return "\n".join(lines) if lines else "No confirmed reservations yet."
    except FileNotFoundError:
        return "No confirmed reservations yet."


def start_mcp_server_thread() -> threading.Thread:
    def _run():
        mcp.run(transport="streamable-http")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    print(f"[MCPServer] Running at {mcp.settings.host}:{MCP_SERVER_PORT}/mcp")
    return thread
