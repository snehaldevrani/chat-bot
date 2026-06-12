import pytest
import uuid
from unittest.mock import patch, MagicMock


# ---------- Email service tests ----------

def test_console_fallback_when_no_credentials(capsys):
    from src.admin.email_service import send_approval_email
    with patch("src.admin.email_service.ADMIN_EMAIL", ""), \
         patch("src.admin.email_service.SENDER_EMAIL", ""), \
         patch("src.admin.email_service.SENDER_APP_PASSWORD", ""):
        result = send_approval_email("test-rid-001", {"name": "John", "surname": "Doe", "car_number": "ABC-123",
                                                       "start_datetime": "2026-06-10 09:00",
                                                       "end_datetime": "2026-06-10 18:00", "space_type": "regular"})
    assert result is False
    captured = capsys.readouterr()
    assert "ADMIN ACTION REQUIRED" in captured.out


def test_email_sends_with_valid_credentials():
    from src.admin.email_service import send_approval_email
    data = {"name": "Jane", "surname": "Smith", "car_number": "XYZ-999",
            "start_datetime": "2026-06-11 10:00", "end_datetime": "2026-06-11 16:00", "space_type": "vip"}
    with patch("src.admin.email_service.ADMIN_EMAIL", "admin@test.com"), \
         patch("src.admin.email_service.SENDER_EMAIL", "sender@gmail.com"), \
         patch("src.admin.email_service.SENDER_APP_PASSWORD", "fakepassword"), \
         patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        result = send_approval_email("test-rid-002", data)
    assert result is True


def test_email_falls_back_on_smtp_error(capsys):
    from src.admin.email_service import send_approval_email
    data = {"name": "Bob", "surname": "Jones", "car_number": "DEF-456",
            "start_datetime": "2026-06-12 08:00", "end_datetime": "2026-06-12 12:00", "space_type": "regular"}
    with patch("src.admin.email_service.ADMIN_EMAIL", "admin@test.com"), \
         patch("src.admin.email_service.SENDER_EMAIL", "sender@gmail.com"), \
         patch("src.admin.email_service.SENDER_APP_PASSWORD", "badpassword"), \
         patch("smtplib.SMTP_SSL", side_effect=Exception("Connection refused")):
        result = send_approval_email("test-rid-003", data)
    assert result is False
    captured = capsys.readouterr()
    assert "ADMIN ACTION REQUIRED" in captured.out


# ---------- Database reservation CRUD tests ----------

def test_create_reservation_persists():
    from src.database.queries import create_reservation, get_reservation
    rid = str(uuid.uuid4())
    data = {"name": "Alice", "surname": "Brown", "car_number": "GHI-789",
            "start_datetime": "2026-06-15 09:00", "end_datetime": "2026-06-15 17:00", "space_type": "regular"}
    create_reservation(rid, "thread-test-001", data)
    record = get_reservation(rid)
    assert record is not None
    assert record.name == "Alice"
    assert record.status == "pending"
    assert record.thread_id == "thread-test-001"


def test_approve_reservation_updates_status():
    from src.database.queries import create_reservation, approve_reservation, get_reservation
    rid = str(uuid.uuid4())
    data = {"name": "Tom", "surname": "Clark", "car_number": "JKL-012",
            "start_datetime": "2026-06-16 10:00", "end_datetime": "2026-06-16 14:00", "space_type": "vip"}
    create_reservation(rid, "thread-test-002", data)
    result = approve_reservation(rid, "Looks good!")
    assert result is True
    record = get_reservation(rid)
    assert record.status == "approved"
    assert record.admin_notes == "Looks good!"
    assert record.reviewed_at is not None


def test_reject_reservation_updates_status():
    from src.database.queries import create_reservation, reject_reservation, get_reservation
    rid = str(uuid.uuid4())
    data = {"name": "Sara", "surname": "Lee", "car_number": "MNO-345",
            "start_datetime": "2026-06-17 08:00", "end_datetime": "2026-06-17 20:00", "space_type": "ev_charging"}
    create_reservation(rid, "thread-test-003", data)
    result = reject_reservation(rid, "Space unavailable.")
    assert result is True
    record = get_reservation(rid)
    assert record.status == "rejected"
    assert record.admin_notes == "Space unavailable."


def test_get_pending_reservations():
    from src.database.queries import create_reservation, get_pending_reservations
    rid = str(uuid.uuid4())
    data = {"name": "Mike", "surname": "White", "car_number": "PQR-678",
            "start_datetime": "2026-06-18 11:00", "end_datetime": "2026-06-18 15:00", "space_type": "handicapped"}
    create_reservation(rid, "thread-test-004", data)
    pending = get_pending_reservations()
    rids = [r.reservation_id for r in pending]
    assert rid in rids


def test_approve_nonexistent_reservation():
    from src.database.queries import approve_reservation
    result = approve_reservation("nonexistent-uuid-0000")
    assert result is False


# ---------- Approval server tests ----------

def test_approval_server_health():
    from src.admin.approval_server import app as fastapi_app
    from fastapi.testclient import TestClient
    client = TestClient(fastapi_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_approval_server_rejects_bad_token():
    from src.admin.approval_server import app as fastapi_app
    from fastapi.testclient import TestClient
    client = TestClient(fastapi_app)
    response = client.get("/approve/some-id?token=wrong-token")
    assert response.status_code == 403


def test_pending_endpoint_returns_list():
    from unittest.mock import patch
    from src.admin.approval_server import app as fastapi_app
    from fastapi.testclient import TestClient
    client = TestClient(fastapi_app)
    with patch("src.admin.approval_server.ADMIN_SECRET_TOKEN", "test-token"):
        response = client.get("/pending?token=test-token")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------- Admin agent tools tests ----------

def test_save_reservation_tool_returns_uuid():
    from src.admin.agent import save_reservation_tool
    result = save_reservation_tool.invoke({
        "thread_id": "thread-tool-test",
        "name": "David", "surname": "Green", "car_number": "STU-901",
        "start_datetime": "2026-06-20 09:00", "end_datetime": "2026-06-20 17:00",
        "space_type": "regular",
    })
    import re
    assert re.match(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", result)


def test_check_status_tool_unknown():
    from src.admin.agent import check_status_tool
    result = check_status_tool.invoke({"reservation_id": "totally-fake-uuid-9999"})
    assert "not found" in result.lower()
