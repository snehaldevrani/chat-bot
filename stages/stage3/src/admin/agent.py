import json
import re
import uuid
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent
from src.config import DIAL_API_KEY, DIAL_ENDPOINT, DIAL_API_VERSION, DIAL_LLM_DEPLOYMENT
from src.admin.email_service import send_approval_email
from src.database.queries import create_reservation, get_reservation

_admin_agent = None


def get_admin_agent():
    global _admin_agent
    if _admin_agent is None:
        llm = AzureChatOpenAI(
            azure_deployment=DIAL_LLM_DEPLOYMENT,
            azure_endpoint=DIAL_ENDPOINT,
            api_key=DIAL_API_KEY,
            api_version=DIAL_API_VERSION,
            temperature=0,
        )
        _admin_agent = create_react_agent(llm, [save_reservation_tool, notify_admin_tool, check_status_tool])
    return _admin_agent


@tool
def save_reservation_tool(
    thread_id: str,
    name: str,
    surname: str,
    car_number: str,
    start_datetime: str,
    end_datetime: str,
    space_type: str,
) -> str:
    """Save a confirmed reservation to the database. Returns the reservation_id."""
    reservation_id = str(uuid.uuid4())
    create_reservation(
        reservation_id,
        thread_id,
        {
            "name": name,
            "surname": surname,
            "car_number": car_number,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "space_type": space_type,
        },
    )
    return reservation_id


@tool
def notify_admin_tool(
    reservation_id: str,
    name: str,
    surname: str,
    car_number: str,
    start_datetime: str,
    end_datetime: str,
    space_type: str,
) -> str:
    """Send an approval request notification to the administrator."""
    sent = send_approval_email(
        reservation_id,
        {
            "name": name,
            "surname": surname,
            "car_number": car_number,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "space_type": space_type,
        },
    )
    return f"Notification sent via {'email' if sent else 'console'}. Reservation ID: {reservation_id}"


@tool
def check_status_tool(reservation_id: str) -> str:
    """Return the current admin approval status for a reservation."""
    record = get_reservation(reservation_id)
    if not record:
        return f"Reservation {reservation_id} not found."
    return f"Status: {record.status}. Notes: {record.admin_notes or 'none'}"


def run_admin_agent(thread_id: str, reservation_data: dict) -> str:
    """Run the admin agent to save and notify. Returns the reservation_id."""
    agent = get_admin_agent()
    safe_data = json.dumps({
        "thread_id": thread_id,
        "name": reservation_data.get("name", ""),
        "surname": reservation_data.get("surname", ""),
        "car_number": reservation_data.get("car_number", ""),
        "start_datetime": reservation_data.get("start_datetime", ""),
        "end_datetime": reservation_data.get("end_datetime", ""),
        "space_type": reservation_data.get("space_type", "regular"),
    }, ensure_ascii=True)
    prompt = (
        "A user has confirmed a parking reservation. "
        "Use the tools to: (1) save it with save_reservation_tool, "
        "(2) notify the admin with notify_admin_tool using the returned reservation_id. "
        f"Reservation details (JSON): {safe_data}\n"
        "Return ONLY the reservation_id UUID string, nothing else."
    )
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    last_msg = result["messages"][-1].content.strip()
    uuids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", last_msg)
    return uuids[0] if uuids else last_msg
