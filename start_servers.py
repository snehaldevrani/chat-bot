"""Start approval + MCP servers for testing, then block."""
import time, uuid
from src.database.seed import seed_database
from src.database.queries import create_reservation
from src.agents.graph import build_graph
from src.admin.approval_server import start_server_thread, set_graph
from src.mcp_server.server import start_mcp_server_thread
from src.config import APPROVAL_SERVER_PORT

seed_database()
fresh_app = build_graph()
set_graph(fresh_app, lambda tid: {"configurable": {"thread_id": tid}})
start_mcp_server_thread()
start_server_thread()
time.sleep(1.5)

# Create a fresh test reservation for Playwright to approve
rid = str(uuid.uuid4())
create_reservation(rid, "playwright-thread", {
    "name": "Snehal", "surname": "Devrani", "car_number": "MH04AB1234",
    "start_datetime": "2026-06-20 09:00", "end_datetime": "2026-06-20 18:00",
    "space_type": "vip"
})
print(f"TEST_RESERVATION_ID={rid}")
# Token intentionally omitted from URLs — authenticate via /admin login page
print(f"APPROVE_URL=http://localhost:{APPROVAL_SERVER_PORT}/admin/dashboard")
print(f"REJECT_URL=http://localhost:{APPROVAL_SERVER_PORT}/admin/dashboard")
print("SERVERS_READY")

while True:
    time.sleep(1)
