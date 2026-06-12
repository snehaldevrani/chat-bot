import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from src.database.models import (
    get_session, ParkingSpace, Pricing, WorkingHours, Reservation,
    User, UserSession, ChatMessage, Notification,
)


def get_availability_summary() -> str:
    session = get_session()
    spaces = session.query(ParkingSpace).all()
    session.close()

    by_type: dict = {}
    for space in spaces:
        t = space.type
        if t not in by_type:
            by_type[t] = {"available": 0, "total": 0}
        by_type[t]["total"] += 1
        if space.status == "available":
            by_type[t]["available"] += 1

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
            if h.is_24_hours:
                lines.append(f"  {day}: Open 24 hours")
            else:
                lines.append(f"  {day}: {h.open_time} - {h.close_time}")
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


# ---------- Reservation CRUD ----------

def create_reservation(reservation_id: str, thread_id: str, data: dict) -> Reservation:
    session = get_session()
    record = Reservation(
        reservation_id=reservation_id,
        thread_id=thread_id,
        name=data.get("name", ""),
        surname=data.get("surname", ""),
        car_number=data.get("car_number", ""),
        start_datetime=data.get("start_datetime", ""),
        end_datetime=data.get("end_datetime", ""),
        space_type=data.get("space_type", "regular"),
        status="pending",
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    session.close()
    return record


def link_user_to_reservation(reservation_id: str, user_id: str) -> None:
    session = get_session()
    record = session.query(Reservation).filter(Reservation.reservation_id == reservation_id).first()
    if record:
        record.user_id = user_id
        session.commit()
    session.close()


def get_reservation(reservation_id: str) -> Reservation | None:
    session = get_session()
    record = session.query(Reservation).filter(Reservation.reservation_id == reservation_id).first()
    session.close()
    return record


def get_pending_reservations() -> list:
    session = get_session()
    records = session.query(Reservation).filter(Reservation.status == "pending").all()
    session.close()
    return records


def get_all_reservations() -> list:
    session = get_session()
    records = session.query(Reservation).order_by(Reservation.id.desc()).all()
    session.close()
    return records


def approve_reservation(reservation_id: str, notes: str = "") -> bool:
    session = get_session()
    record = session.query(Reservation).filter(Reservation.reservation_id == reservation_id).first()
    if not record:
        session.close()
        return False
    record.status = "approved"
    record.reviewed_at = datetime.now(timezone.utc).isoformat()
    record.admin_notes = notes
    session.commit()
    session.close()
    return True


def reject_reservation(reservation_id: str, notes: str = "") -> bool:
    session = get_session()
    record = session.query(Reservation).filter(Reservation.reservation_id == reservation_id).first()
    if not record:
        session.close()
        return False
    record.status = "rejected"
    record.reviewed_at = datetime.now(timezone.utc).isoformat()
    record.admin_notes = notes or "Rejected by administrator."
    session.commit()
    session.close()
    return True


# ---------- User CRUD ----------

def _hash_password(password: str) -> tuple[str, str]:
    salt = os.urandom(32).hex()
    hash_ = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000).hex()
    return hash_, salt


def create_user(email: str, password: str, first_name: str, last_name: str,
                car_number: str = None, role: str = "user") -> User:
    hash_, salt = _hash_password(password)
    session = get_session()
    user = User(
        user_id=str(uuid.uuid4()),
        email=email.lower().strip(),
        password_hash=hash_,
        password_salt=salt,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        car_number=car_number.strip() if car_number else None,
        role=role,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def get_user_by_email(email: str) -> User | None:
    session = get_session()
    user = session.query(User).filter(User.email == email.lower().strip()).first()
    session.close()
    return user


def get_user_by_id(user_id: str) -> User | None:
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    session.close()
    return user


def verify_password(user: User, password: str) -> bool:
    hash_ = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), user.password_salt.encode(), 260_000
    ).hex()
    return hmac.compare_digest(hash_, user.password_hash)


def update_last_login(user_id: str) -> None:
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    if user:
        user.last_login = datetime.now(timezone.utc).isoformat()
        session.commit()
    session.close()


# ---------- Session CRUD ----------

def create_session(user_id: str) -> str:
    from src.config import SESSION_TTL_DAYS
    token = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SESSION_TTL_DAYS)
    session = get_session()
    s = UserSession(
        session_token=token,
        user_id=user_id,
        created_at=now.isoformat(),
        expires_at=expires.isoformat(),
        is_valid=True,
    )
    session.add(s)
    session.commit()
    session.close()
    return token


def get_session_user(token: str) -> User | None:
    if not token:
        return None
    db = get_session()
    s = db.query(UserSession).filter(
        UserSession.session_token == token,
        UserSession.is_valid == True,
    ).first()
    if not s:
        db.close()
        return None
    try:
        expires = datetime.fromisoformat(s.expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            db.close()
            return None
    except Exception:
        db.close()
        return None
    user_id = s.user_id
    db.close()
    return get_user_by_id(user_id)


def invalidate_session(token: str) -> None:
    session = get_session()
    s = session.query(UserSession).filter(UserSession.session_token == token).first()
    if s:
        s.is_valid = False
        session.commit()
    session.close()


# ---------- Chat Message CRUD ----------

def save_chat_message(thread_id: str, role: str, content: str,
                      user_id: str = None, chat_title: str = None) -> None:
    session = get_session()
    msg = ChatMessage(
        thread_id=thread_id,
        user_id=user_id,
        role=role,
        content=content,
        created_at=datetime.now(timezone.utc).isoformat(),
        chat_title=chat_title,
    )
    session.add(msg)
    session.commit()
    session.close()


def get_chat_messages(thread_id: str) -> list:
    session = get_session()
    msgs = session.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id
    ).order_by(ChatMessage.id.asc()).all()
    session.close()
    return msgs


def get_thread_title(thread_id: str) -> str | None:
    session = get_session()
    msg = session.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id,
        ChatMessage.chat_title != None,
    ).first()
    session.close()
    return msg.chat_title if msg else None


def get_user_chat_sessions(user_id: str) -> list:
    session = get_session()
    rows = (
        session.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.chat_title != None)
        .order_by(ChatMessage.id.desc())
        .all()
    )
    session.close()
    seen = {}
    for row in rows:
        if row.thread_id not in seen:
            seen[row.thread_id] = {
                "thread_id": row.thread_id,
                "chat_title": row.chat_title,
                "last_active": row.created_at,
            }
    return list(seen.values())


# ---------- Notification CRUD ----------

def create_notification(user_id: str, reservation_id: str,
                        message: str, notification_type: str) -> None:
    session = get_session()
    n = Notification(
        notification_id=str(uuid.uuid4()),
        user_id=user_id,
        reservation_id=reservation_id,
        message=message,
        is_read=False,
        created_at=datetime.now(timezone.utc).isoformat(),
        notification_type=notification_type,
    )
    session.add(n)
    session.commit()
    session.close()


def get_user_notifications(user_id: str) -> list:
    session = get_session()
    notes = session.query(Notification).filter(
        Notification.user_id == user_id
    ).order_by(Notification.id.desc()).all()
    session.close()
    return notes


def get_unread_count(user_id: str) -> int:
    session = get_session()
    count = session.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).count()
    session.close()
    return count


def mark_notifications_read(user_id: str) -> None:
    session = get_session()
    session.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).update({"is_read": True})
    session.commit()
    session.close()
