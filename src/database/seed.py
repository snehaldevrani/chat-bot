from sqlalchemy import text
from src.database.models import get_engine, get_session, Base, ParkingSpace, Pricing, WorkingHours, User

SPACES_DATA = [
    # Ground Floor — 10 regular + 2 handicapped
    {"space_number": "G-01", "level": "Ground", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "G-02", "level": "Ground", "type": "regular", "size": "standard", "status": "occupied"},
    {"space_number": "G-03", "level": "Ground", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "G-04", "level": "Ground", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "G-05", "level": "Ground", "type": "regular", "size": "standard", "status": "reserved"},
    {"space_number": "G-06", "level": "Ground", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "G-07", "level": "Ground", "type": "regular", "size": "large", "status": "occupied"},
    {"space_number": "G-08", "level": "Ground", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "G-09", "level": "Ground", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "G-10", "level": "Ground", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "G-H1", "level": "Ground", "type": "handicapped", "size": "large", "status": "available"},
    {"space_number": "G-H2", "level": "Ground", "type": "handicapped", "size": "large", "status": "occupied"},
    # Level 1 — 15 regular + 3 EV
    {"space_number": "L1-01", "level": "L1", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L1-02", "level": "L1", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L1-03", "level": "L1", "type": "regular", "size": "compact", "status": "occupied"},
    {"space_number": "L1-04", "level": "L1", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L1-05", "level": "L1", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "L1-06", "level": "L1", "type": "regular", "size": "standard", "status": "reserved"},
    {"space_number": "L1-07", "level": "L1", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L1-08", "level": "L1", "type": "regular", "size": "large", "status": "available"},
    {"space_number": "L1-09", "level": "L1", "type": "regular", "size": "standard", "status": "occupied"},
    {"space_number": "L1-10", "level": "L1", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "L1-11", "level": "L1", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L1-12", "level": "L1", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L1-13", "level": "L1", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "L1-14", "level": "L1", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L1-15", "level": "L1", "type": "regular", "size": "standard", "status": "occupied"},
    {"space_number": "L1-EV1", "level": "L1", "type": "ev_charging", "size": "standard", "status": "available"},
    {"space_number": "L1-EV2", "level": "L1", "type": "ev_charging", "size": "standard", "status": "occupied"},
    {"space_number": "L1-EV3", "level": "L1", "type": "ev_charging", "size": "standard", "status": "available"},
    # Level 2 — 10 regular + 5 VIP
    {"space_number": "L2-01", "level": "L2", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L2-02", "level": "L2", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L2-03", "level": "L2", "type": "regular", "size": "compact", "status": "occupied"},
    {"space_number": "L2-04", "level": "L2", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L2-05", "level": "L2", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L2-06", "level": "L2", "type": "regular", "size": "large", "status": "reserved"},
    {"space_number": "L2-07", "level": "L2", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L2-08", "level": "L2", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "L2-09", "level": "L2", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "L2-10", "level": "L2", "type": "regular", "size": "standard", "status": "occupied"},
    {"space_number": "L2-VIP1", "level": "L2", "type": "vip", "size": "large", "status": "available"},
    {"space_number": "L2-VIP2", "level": "L2", "type": "vip", "size": "large", "status": "reserved"},
    {"space_number": "L2-VIP3", "level": "L2", "type": "vip", "size": "large", "status": "available"},
    {"space_number": "L2-VIP4", "level": "L2", "type": "vip", "size": "large", "status": "available"},
    {"space_number": "L2-VIP5", "level": "L2", "type": "vip", "size": "large", "status": "occupied"},
    # Basement — 8 regular + 2 EV + 2 handicapped
    {"space_number": "B-01", "level": "Basement", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "B-02", "level": "Basement", "type": "regular", "size": "standard", "status": "occupied"},
    {"space_number": "B-03", "level": "Basement", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "B-04", "level": "Basement", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "B-05", "level": "Basement", "type": "regular", "size": "compact", "status": "available"},
    {"space_number": "B-06", "level": "Basement", "type": "regular", "size": "standard", "status": "reserved"},
    {"space_number": "B-07", "level": "Basement", "type": "regular", "size": "standard", "status": "available"},
    {"space_number": "B-08", "level": "Basement", "type": "regular", "size": "large", "status": "available"},
    {"space_number": "B-EV1", "level": "Basement", "type": "ev_charging", "size": "standard", "status": "available"},
    {"space_number": "B-EV2", "level": "Basement", "type": "ev_charging", "size": "standard", "status": "available"},
    {"space_number": "B-H1", "level": "Basement", "type": "handicapped", "size": "large", "status": "available"},
    {"space_number": "B-H2", "level": "Basement", "type": "handicapped", "size": "large", "status": "occupied"},
]

PRICING_DATA = [
    {"space_type": "regular", "hourly_rate": 3.0, "daily_rate": 20.0, "monthly_rate": 150.0},
    {"space_type": "handicapped", "hourly_rate": 2.0, "daily_rate": 15.0, "monthly_rate": 100.0},
    {"space_type": "ev_charging", "hourly_rate": 5.0, "daily_rate": 35.0, "monthly_rate": 250.0},
    {"space_type": "vip", "hourly_rate": 8.0, "daily_rate": 50.0, "monthly_rate": 350.0},
]

HOURS_DATA = [
    {"day_of_week": "Monday", "open_time": "06:00", "close_time": "22:00", "is_24_hours": False},
    {"day_of_week": "Tuesday", "open_time": "06:00", "close_time": "22:00", "is_24_hours": False},
    {"day_of_week": "Wednesday", "open_time": "06:00", "close_time": "22:00", "is_24_hours": False},
    {"day_of_week": "Thursday", "open_time": "06:00", "close_time": "22:00", "is_24_hours": False},
    {"day_of_week": "Friday", "open_time": "06:00", "close_time": "22:00", "is_24_hours": False},
    {"day_of_week": "Saturday", "open_time": "07:00", "close_time": "22:00", "is_24_hours": False},
    {"day_of_week": "Sunday", "open_time": "08:00", "close_time": "20:00", "is_24_hours": False},
]


def seed_database():
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Migrate: add user_id column to reservations if it doesn't exist yet
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE reservations ADD COLUMN user_id VARCHAR(36)"))
            conn.commit()
        except Exception:
            pass  # Column already exists — idempotent

    session = get_session()

    if session.query(ParkingSpace).count() > 0:
        session.close()
        _seed_admin_user()
        return

    for space in SPACES_DATA:
        session.add(ParkingSpace(**space))
    for price in PRICING_DATA:
        session.add(Pricing(**price))
    for hours in HOURS_DATA:
        session.add(WorkingHours(**hours))

    session.commit()
    session.close()
    print("Database seeded successfully.")

    # Seed admin user if not already present
    _seed_admin_user()


def _seed_admin_user() -> None:
    from src.database.queries import get_user_by_email, create_user
    if not get_user_by_email("admin@email.com"):
        create_user(
            email="admin@email.com",
            password="admin123",
            first_name="Admin",
            last_name="CityPark",
            role="admin",
        )
        print("Admin user seeded: admin@email.com / admin123")
