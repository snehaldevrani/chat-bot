import uuid
from pathlib import Path

from fastapi.testclient import TestClient


def test_mcp_writer_uses_required_four_column_format(tmp_path, monkeypatch):
    from src.mcp_server import server

    log_path = tmp_path / "reservations.txt"
    monkeypatch.setattr(server, "RESERVATIONS_FILE", str(log_path))
    monkeypatch.setattr(server, "_LOCK_FILE", str(log_path) + ".lock")
    monkeypatch.setattr(server, "MCP_SECRET_TOKEN", "secret")

    result = server.write_confirmed_reservation(
        token="secret",
        reservation_id=str(uuid.uuid4()),
        name="Snehal",
        surname="Devrani",
        car_number="MH04AB1234",
        start_datetime="2026-06-15 09:00",
        end_datetime="2026-06-15 18:00",
        approval_time="2026-06-14 10:00:00",
        space_type="regular",
    )

    assert result.startswith("OK")
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    assert lines[-1].split(" | ") == [
        "Snehal Devrani",
        "MH04AB1234",
        "2026-06-15 09:00 to 2026-06-15 18:00",
        "2026-06-14 10:00:00",
    ]


def test_approval_server_calls_mcp_on_approve(monkeypatch):
    from src.admin import approval_server
    from src.config import ADMIN_SECRET_TOKEN
    from src.database.queries import create_reservation, get_reservation

    calls = []
    monkeypatch.setattr(approval_server, "_write_to_mcp", lambda record: calls.append(record.reservation_id) or "OK")
    reservation_id = str(uuid.uuid4())
    create_reservation(reservation_id, "thread", {
        "name": "A",
        "surname": "B",
        "car_number": "CAR123",
        "start_datetime": "2026-06-15 09:00",
        "end_datetime": "2026-06-15 18:00",
        "space_type": "regular",
    })

    response = TestClient(approval_server.app).get(f"/approve/{reservation_id}", params={"token": ADMIN_SECRET_TOKEN})

    assert response.status_code == 200
    assert calls == [reservation_id]
    assert get_reservation(reservation_id).status == "approved"


def test_approval_server_rejects_reservation_without_mcp_write(monkeypatch):
    from src.admin import approval_server
    from src.config import ADMIN_SECRET_TOKEN
    from src.database.queries import create_reservation, get_reservation

    mcp_calls = []
    monkeypatch.setattr(approval_server, "_write_to_mcp", lambda record: mcp_calls.append(record.reservation_id) or "OK")
    reservation_id = str(uuid.uuid4())
    create_reservation(reservation_id, "thread", {
        "name": "E",
        "surname": "F",
        "car_number": "REJ456",
        "start_datetime": "2026-07-02 09:00",
        "end_datetime": "2026-07-02 17:00",
        "space_type": "vip",
    })

    response = TestClient(approval_server.app).get(
        f"/reject/{reservation_id}",
        params={"token": ADMIN_SECRET_TOKEN, "notes": "Overbooked."},
    )

    assert response.status_code == 200
    assert "rejected" in response.text.lower()
    assert get_reservation(reservation_id).status == "rejected"
    assert mcp_calls == [], "MCP must NOT be called on rejection"


def test_stage3_has_mcp_but_no_graph_module():
    import importlib.util

    assert importlib.util.find_spec("src.mcp_server") is not None
    assert importlib.util.find_spec("src.agents.graph") is None
