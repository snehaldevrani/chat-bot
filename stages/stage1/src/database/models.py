import os
from sqlalchemy import Boolean, Column, Float, Integer, String, Text, create_engine, text
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
    status = Column(String, nullable=False, default="collected")
    submitted_at = Column(String, nullable=False)
    reviewed_at = Column(String, nullable=True)
    admin_notes = Column(Text, nullable=True)


def get_engine():
    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
    return create_engine(f"sqlite:///{SQLITE_DB_PATH}", connect_args={"check_same_thread": False})


def _run_migrations(engine) -> None:
    with engine.connect() as conn:
        for ddl in [
            "ALTER TABLE reservations ADD COLUMN reviewed_at VARCHAR",
            "ALTER TABLE reservations ADD COLUMN admin_notes TEXT",
        ]:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass


def get_session():
    engine = get_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)
    Session = sessionmaker(bind=engine)
    return Session()
