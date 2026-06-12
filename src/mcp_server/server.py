import hmac
import os
import threading
import filelock
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from src.config import MCP_SECRET_TOKEN, MCP_SERVER_PORT, RESERVATIONS_FILE

mcp = FastMCP(
    "CityPark Reservation Writer",
    host="127.0.0.1",
    port=MCP_SERVER_PORT,
)

_LOCK_FILE = RESERVATIONS_FILE + ".lock"
_HEADER = (
    "# CityPark Premium Parking — Confirmed Reservations Log\n"
    "# Format: Name | Car Number | Reservation Period | Approval Time | Space Type | Reservation ID\n"
)


def _ensure_file() -> None:
    path = Path(RESERVATIONS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_HEADER, encoding="utf-8")


def _already_written(reservation_id: str) -> bool:
    try:
        content = Path(RESERVATIONS_FILE).read_text(encoding="utf-8")
        return reservation_id[:8].upper() in content
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
    Write a confirmed parking reservation to the reservations log file.
    Requires a valid secret token. Idempotent — skips duplicate reservation_ids.
    """
    if not hmac.compare_digest(token, MCP_SECRET_TOKEN):
        return "ERROR: Unauthorized. Invalid token."

    if _already_written(reservation_id):
        return f"SKIPPED: Reservation {reservation_id[:8]} already logged."

    _ensure_file()

    full_name = f"{name} {surname}"
    period = f"{start_datetime} to {end_datetime}"
    space_label = space_type.replace("_", " ").title()
    short_id = reservation_id[:8].upper()

    line = f"{full_name} | {car_number} | {period} | {approval_time} | {space_label} | {short_id}\n"

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
        lines = [l for l in content.splitlines() if l and not l.startswith("#")]
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
