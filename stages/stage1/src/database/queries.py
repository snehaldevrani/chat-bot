import uuid
from datetime import datetime, timezone
from src.database.models import get_session, ParkingSpace, Pricing, WorkingHours, Reservation


def get_availability_summary() -> str:
    session = get_session()
    spaces = session.query(ParkingSpace).all()
    session.close()

    by_type: dict = {}
    for space in spaces:
        stats = by_type.setdefault(space.type, {"available": 0, "total": 0})
        stats["total"] += 1
        if space.status == "available":
            stats["available"] += 1

    lines = ["Current Space Availability:"]
    for space_type, counts in sorted(by_type.items()):
        label = space_type.replace("_", " ").title()
        lines.append(f"  {label}: {counts['available']} available out of {counts['total']} total")
    return "\n".join(lines)


def get_pricing_summary() -> str:
    session = get_session()
    prices = session.query(Pricing).all()
    session.close()

    lines = ["Current Pricing:"]
    for p in prices:
        label = p.space_type.replace("_", " ").title()
        lines.append(f"  {label}: ${p.hourly_rate:.2f}/hr | ${p.daily_rate:.2f}/day | ${p.monthly_rate:.2f}/month")
    return "\n".join(lines)


def get_hours_summary() -> str:
    session = get_session()
    hours = session.query(WorkingHours).all()
    session.close()

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours_map = {h.day_of_week: h for h in hours}
    lines = ["Operating Hours:"]
    for day in day_order:
        h = hours_map.get(day)
        if h:
            lines.append(f"  {day}: {'Open 24 hours' if h.is_24_hours else f'{h.open_time} - {h.close_time}'}")
    return "\n".join(lines)


def get_available_spaces(space_type: str = None) -> list:
    session = get_session()
    query = session.query(ParkingSpace).filter(ParkingSpace.status == "available")
    if space_type:
        query = query.filter(ParkingSpace.type == space_type.lower())
    spaces = query.all()
    session.close()
    return spaces


def get_pricing_for_type(space_type: str) -> Pricing | None:
    session = get_session()
    price = session.query(Pricing).filter(Pricing.space_type == space_type.lower()).first()
    session.close()
    return price


def create_reservation(reservation_id: str | None, thread_id: str, data: dict) -> Reservation:
    session = get_session()
    record = Reservation(
        reservation_id=reservation_id or str(uuid.uuid4()),
        thread_id=thread_id,
        name=data.get("name", ""),
        surname=data.get("surname", ""),
        car_number=data.get("car_number", ""),
        start_datetime=data.get("start_datetime", ""),
        end_datetime=data.get("end_datetime", ""),
        space_type=data.get("space_type", "regular"),
        status=data.get("status", "collected"),
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    session.close()
    return record


def get_reservation(reservation_id: str) -> Reservation | None:
    session = get_session()
    record = session.query(Reservation).filter(Reservation.reservation_id == reservation_id).first()
    session.close()
    return record
