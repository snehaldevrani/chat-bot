import json
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


def test_admin_agent_creates_pending_reservation(monkeypatch):
    from src.admin import agent
    from src.database.queries import get_reservation
    from langchain_core.messages import AIMessage

    monkeypatch.setattr(agent, "send_approval_email", lambda *args, **kwargs: False)

    def _fake_invoke(inputs):
        content = inputs["messages"][0]["content"]
        data = json.loads(content.split("JSON): ")[1].split("\n")[0])
        rid = agent.save_reservation_tool.invoke(
            {k: data[k] for k in ["thread_id", "name", "surname", "car_number",
                                   "start_datetime", "end_datetime", "space_type"]}
        )
        agent.notify_admin_tool.invoke({
            "reservation_id": rid,
            **{k: data[k] for k in ["name", "surname", "car_number",
                                     "start_datetime", "end_datetime", "space_type"]},
        })
        return {"messages": [AIMessage(content=rid)]}

    mock_agent = MagicMock()
    mock_agent.invoke.side_effect = _fake_invoke
    monkeypatch.setattr(agent, "_admin_agent", mock_agent)

    reservation_id = agent.run_admin_agent(str(uuid.uuid4()), {
        "name": "Snehal",
        "surname": "Devrani",
        "car_number": "MH04AB1234",
        "start_datetime": "2026-06-15 09:00",
        "end_datetime": "2026-06-15 18:00",
        "space_type": "regular",
    })

    record = get_reservation(reservation_id)
    assert record is not None
    assert record.status == "pending"


def test_approval_server_approves_without_mcp(monkeypatch):
    from src.admin.approval_server import app
    from src.config import ADMIN_SECRET_TOKEN
    from src.database.queries import create_reservation, get_reservation

    reservation_id = str(uuid.uuid4())
    create_reservation(reservation_id, "thread", {
        "name": "A",
        "surname": "B",
        "car_number": "CAR123",
        "start_datetime": "2026-06-15 09:00",
        "end_datetime": "2026-06-15 18:00",
        "space_type": "regular",
    })
    client = TestClient(app)
    response = client.get(f"/approve/{reservation_id}", params={"token": ADMIN_SECRET_TOKEN})

    assert response.status_code == 200
    assert get_reservation(reservation_id).status == "approved"


def test_approval_server_rejects_reservation():
    from src.admin.approval_server import app
    from src.config import ADMIN_SECRET_TOKEN
    from src.database.queries import create_reservation, get_reservation

    reservation_id = str(uuid.uuid4())
    create_reservation(reservation_id, "thread", {
        "name": "C",
        "surname": "D",
        "car_number": "REJ123",
        "start_datetime": "2026-07-01 09:00",
        "end_datetime": "2026-07-01 17:00",
        "space_type": "regular",
    })
    client = TestClient(app)
    response = client.get(
        f"/reject/{reservation_id}",
        params={"token": ADMIN_SECRET_TOKEN, "notes": "No spaces available."},
    )

    assert response.status_code == 200
    assert "rejected" in response.text.lower()
    record = get_reservation(reservation_id)
    assert record.status == "rejected"
    assert record.admin_notes == "No spaces available."


def test_stage2_has_no_mcp_or_graph_modules():
    import importlib.util

    assert importlib.util.find_spec("src.mcp_server") is None
    assert importlib.util.find_spec("src.agents.graph") is None
