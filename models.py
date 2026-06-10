from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

db = SQLAlchemy()


class User(db.Model):
    """User account for authentication."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class TimeKeeper(db.Model):
    __tablename__ = "time_keepers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    parser_module = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")

    events = db.relationship("Event", back_populates="time_keeper")


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    track = db.Column(db.String(200), default="")
    year = db.Column(db.Integer, nullable=True)
    championship = db.Column(db.String(200), default="")
    event_date = db.Column(db.Date, nullable=True)
    time_keeper_id = db.Column(db.Integer, db.ForeignKey("time_keepers.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    time_keeper = db.relationship("TimeKeeper", back_populates="events")
    sessions = db.relationship(
        "Session",
        back_populates="event",
        order_by="Session.start_time",
        cascade="all, delete-orphan",
    )


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    session_type = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    event = db.relationship("Event", back_populates="sessions")
    laps = db.relationship("LapRecord", back_populates="session",
                           order_by="LapRecord.lap_number", cascade="all, delete-orphan")
    standings = db.relationship("Standing", back_populates="session",
                                order_by="Standing.position", cascade="all, delete-orphan")


class Standing(db.Model):
    """Classification / race result per car."""
    __tablename__ = "standings"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    car_number = db.Column(db.String(20), nullable=False)
    team_name = db.Column(db.String(200), default="")
    class_name = db.Column(db.String(100), default="")
    nationality = db.Column(db.String(10), default="")
    total_time = db.Column(db.Float, nullable=True)
    gap = db.Column(db.Float, nullable=True)
    diff = db.Column(db.Float, nullable=True)
    laps_completed = db.Column(db.Integer, nullable=True)
    fastest_lap = db.Column(db.Float, nullable=True)
    fastest_lap_no = db.Column(db.Integer, nullable=True)
    fastest_lap_speed = db.Column(db.Float, nullable=True)
    pit_stops = db.Column(db.Integer, default=0)
    is_classified = db.Column(db.Boolean, default=True)

    session = db.relationship("Session", back_populates="standings")


class LapRecord(db.Model):
    __tablename__ = "lap_records"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    car_number = db.Column(db.String(20), nullable=False)
    driver_name = db.Column(db.String(200), default="")
    category = db.Column(db.String(100), default="")
    lap_number = db.Column(db.Integer, nullable=False)
    lap_time = db.Column(db.Float, nullable=True)
    sector_1 = db.Column(db.Float, nullable=True)
    sector_2 = db.Column(db.Float, nullable=True)
    sector_3 = db.Column(db.Float, nullable=True)
    gap = db.Column(db.Float, nullable=True)
    speed = db.Column(db.Float, nullable=True)         # general avg speed, kept for compat
    speed_trap_1 = db.Column(db.Float, nullable=True)
    speed_trap_2 = db.Column(db.Float, nullable=True)
    speed_trap_3 = db.Column(db.Float, nullable=True)
    speed_trap_4 = db.Column(db.Float, nullable=True)
    position = db.Column(db.Integer, nullable=True)
    is_best = db.Column(db.Boolean, default=False)
    out_lap = db.Column(db.Boolean, default=False)
    in_lap = db.Column(db.Boolean, default=False)
    time_of_day = db.Column(db.String(20), default="")
    session_time = db.Column(db.Float, nullable=True)

    session = db.relationship("Session", back_populates="laps")
