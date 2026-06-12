import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Text, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker
from src.config import SQLITE_DB_PATH

Base = declarative_base()


class ParkingSpace(Base):
    __tablename__ = "parking_spaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_number = Column(String, unique=True, nullable=False)
    level = Column(String, nullable=False)
    type = Column(String, nullable=False)
    size = Column(String, nullable=False)
    status = Column(String, nullable=False, default="available")


class Pricing(Base):
    __tablename__ = "pricing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_type = Column(String, unique=True, nullable=False)
    hourly_rate = Column(Float, nullable=False)
    daily_rate = Column(Float, nullable=False)
    monthly_rate = Column(Float, nullable=False)


class WorkingHours(Base):
    __tablename__ = "working_hours"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day_of_week = Column(String, unique=True, nullable=False)
    open_time = Column(String, nullable=False)
    close_time = Column(String, nullable=False)
    is_24_hours = Column(Boolean, default=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(String, unique=True, nullable=False)
    thread_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    surname = Column(String, nullable=False)
    car_number = Column(String, nullable=False)
    start_datetime = Column(String, nullable=False)
    end_datetime = Column(String, nullable=False)
    space_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    submitted_at = Column(String, nullable=False)
    reviewed_at = Column(String, nullable=True)
    admin_notes = Column(Text, nullable=True)
    user_id = Column(String(36), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), unique=True, nullable=False)
    email = Column(String(254), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    password_salt = Column(String(64), nullable=False)
    first_name = Column(String(60), nullable=False)
    last_name = Column(String(60), nullable=False)
    car_number = Column(String(20), nullable=True)
    role = Column(String(10), nullable=False, default="user")
    created_at = Column(String, nullable=False)
    last_login = Column(String, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_token = Column(String(64), unique=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)
    is_valid = Column(Boolean, nullable=False, default=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=True)
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(String, nullable=False)
    chat_title = Column(String(100), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(String(36), unique=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    reservation_id = Column(String(36), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(String, nullable=False)
    notification_type = Column(String(20), nullable=False)


def get_engine():
    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
    return create_engine(f"sqlite:///{SQLITE_DB_PATH}", connect_args={"check_same_thread": False})


def _run_migrations(engine) -> None:
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE reservations ADD COLUMN user_id VARCHAR(36)"))
            conn.commit()
        except Exception:
            pass  # Column already exists


def get_session():
    engine = get_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)
    Session = sessionmaker(bind=engine)
    return Session()
