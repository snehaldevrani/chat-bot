import uuid
from src.database.queries import (
    get_availability_summary,
    get_pricing_summary,
    get_hours_summary,
    create_reservation,
    get_reservation,
    approve_reservation,
    reject_reservation,
    get_pending_reservations,
)


# ---------- Summary queries ----------

def test_availability_summary_is_string():
    result = get_availability_summary()
    assert isinstance(result, str)
    assert "Availability" in result


def test_pricing_summary_is_string():
    result = get_pricing_summary()
    assert isinstance(result, str)
    assert "Pricing" in result


def test_hours_summary_is_string():
    result = get_hours_summary()
    assert isinstance(result, str)
    assert "Hours" in result


# ---------- Reservation CRUD ----------

def test_create_reservation_defaults_to_pending():
    rid = str(uuid.uuid4())
    create_reservation(rid, "thread-s2-1", {
        "name": "Alice", "surname": "Brown", "car_number": "AB01XY",
        "start_datetime": "2026-06-15 09:00", "end_datetime": "2026-06-15 17:00",
        "space_type": "regular",
    })
    assert get_reservation(rid).status == "pending"


def test_get_reservation_not_found():
    assert get_reservation("nonexistent-stage2-0000") is None


# ---------- Approval workflow ----------

def test_approve_reservation_sets_approved():
    rid = str(uuid.uuid4())
    create_reservation(rid, "thread-s2-2", {
        "name": "Tom", "surname": "Clark", "car_number": "TC02ZZ",
        "start_datetime": "2026-06-16 10:00", "end_datetime": "2026-06-16 14:00",
        "space_type": "vip",
    })
    result = approve_reservation(rid, "Approved by admin")
    assert result is True
    record = get_reservation(rid)
    assert record.status == "approved"
    assert record.admin_notes == "Approved by admin"
    assert record.reviewed_at is not None


def test_reject_reservation_sets_rejected():
    rid = str(uuid.uuid4())
    create_reservation(rid, "thread-s2-3", {
        "name": "Sara", "surname": "Lee", "car_number": "SL03AA",
        "start_datetime": "2026-06-17 08:00", "end_datetime": "2026-06-17 20:00",
        "space_type": "ev_charging",
    })
    result = reject_reservation(rid, "No spaces available")
    assert result is True
    assert get_reservation(rid).status == "rejected"


def test_approve_nonexistent_returns_false():
    assert approve_reservation("totally-fake-uuid-stage2") is False


def test_get_pending_includes_new_reservation():
    rid = str(uuid.uuid4())
    create_reservation(rid, "thread-s2-4", {
        "name": "Mike", "surname": "White", "car_number": "MW04BB",
        "start_datetime": "2026-06-18 11:00", "end_datetime": "2026-06-18 15:00",
        "space_type": "handicapped",
    })
    ids = [r.reservation_id for r in get_pending_reservations()]
    assert rid in ids
