import uuid
from src.database.queries import (
    get_availability_summary,
    get_pricing_summary,
    get_hours_summary,
    create_reservation,
    get_reservation,
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

def test_create_reservation_persists():
    rid = str(uuid.uuid4())
    create_reservation(rid, "thread-db-test", {
        "name": "Alice", "surname": "Brown", "car_number": "AB01XY",
        "start_datetime": "2026-06-15 09:00", "end_datetime": "2026-06-15 17:00",
        "space_type": "regular",
    })
    record = get_reservation(rid)
    assert record is not None
    assert record.name == "Alice"
    assert record.car_number == "AB01XY"


def test_create_reservation_default_status_collected():
    rid = str(uuid.uuid4())
    create_reservation(rid, "thread-db-test2", {
        "name": "Bob", "surname": "Smith", "car_number": "BC02YZ",
        "start_datetime": "2026-06-16 10:00", "end_datetime": "2026-06-16 12:00",
        "space_type": "vip",
    })
    record = get_reservation(rid)
    assert record.status == "collected"


def test_get_reservation_not_found_returns_none():
    assert get_reservation("nonexistent-0000-0000") is None
