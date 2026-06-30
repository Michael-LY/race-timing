import os
import secrets

from flask import Flask, session as flask_session, request, abort
from sqlalchemy import inspect, text

from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, UPLOAD_FOLDER, SECRET_KEY
from models import db, TimeKeeper, User


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["SECRET_KEY"] = SECRET_KEY

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    db_dir = SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")
    if db_dir:
        os.makedirs(os.path.dirname(db_dir), exist_ok=True)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _ensure_session_sort_order_column()
        _ensure_lap_record_time_columns()
        _ensure_car_model_columns()
        _ensure_series_color_columns()
        _ensure_model_color_columns()
        _ensure_gap_text_columns()
        _ensure_event_is_hidden_column()
        _ensure_track_limit_column()
        _seed_time_keepers()
        _seed_admin()

    # Context processor: inject current_user and csrf_token into all templates
    @app.context_processor
    def inject_globals():
        user_id = flask_session.get("user_id")
        user = None
        if user_id:
            user = db.session.get(User, user_id)
        # Eagerly generate CSRF token so it's always available
        if "_csrf_token" not in flask_session:
            flask_session["_csrf_token"] = secrets.token_hex(32)
        return dict(current_user=user, csrf_token=flask_session["_csrf_token"])

    # CSRF protection for all POST requests
    @app.before_request
    def csrf_protect():
        if request.method != "POST":
            return
        # Skip CSRF for API endpoints (token-based, no session)
        if request.path.startswith("/api/"):
            return
        token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not _verify_csrf_token(token):
            abort(403)

    from routes import bp
    app.register_blueprint(bp)

    # Template filter: extract ISO week number from a date
    @app.template_filter("isoweek")
    def _iso_week_filter(date):
        if date is None:
            return None
        return date.isocalendar()[1]

    return app


def _verify_csrf_token(token: str) -> bool:
    """Verify a CSRF token against the session token."""
    expected = flask_session.get("_csrf_token")
    if not expected or not token:
        return False
    return secrets.compare_digest(token, expected)


def _ensure_session_sort_order_column():
    inspector = inspect(db.engine)
    if "sessions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("sessions")}
    if "sort_order" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE sessions ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))


def _ensure_lap_record_time_columns():
    inspector = inspect(db.engine)
    if "lap_records" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("lap_records")}
    if "time_out_lap" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE lap_records ADD COLUMN time_out_lap FLOAT"))
    if "time_in_lap" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE lap_records ADD COLUMN time_in_lap FLOAT"))


def _ensure_car_model_columns():
    inspector = inspect(db.engine)
    # standings.car_model
    if "standings" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("standings")}
        if "car_model" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN car_model VARCHAR(100) DEFAULT ''"))
    # lap_records.car_model
    if "lap_records" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("lap_records")}
        if "car_model" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE lap_records ADD COLUMN car_model VARCHAR(100) DEFAULT ''"))


def _ensure_series_color_columns():
    inspector = inspect(db.engine)
    # standings.series_color
    if "standings" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("standings")}
        if "series_color" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN series_color VARCHAR(20) DEFAULT ''"))
    # lap_records.series_color
    if "lap_records" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("lap_records")}
        if "series_color" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE lap_records ADD COLUMN series_color VARCHAR(20) DEFAULT ''"))


def _ensure_model_color_columns():
    inspector = inspect(db.engine)
    for table in ("standings", "lap_records", "car_configs"):
        if table in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "model_color" not in columns:
                with db.engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN model_color VARCHAR(20) DEFAULT ''"))


def _ensure_gap_text_columns():
    inspector = inspect(db.engine)
    if "standings" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("standings")}
        if "gap_text" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN gap_text VARCHAR(50) DEFAULT ''"))
        if "diff_text" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN diff_text VARCHAR(50) DEFAULT ''"))


def _ensure_event_is_hidden_column():
    inspector = inspect(db.engine)
    if "events" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("events")}
    if "is_hidden" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE events ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0"))


def _ensure_track_limit_column():
    inspector = inspect(db.engine)
    if "lap_records" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("lap_records")}
    if "track_limit" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE lap_records ADD COLUMN track_limit BOOLEAN NOT NULL DEFAULT 0"))


def _seed_time_keepers():
    from parsers import PARSER_REGISTRY
    for key, parser in PARSER_REGISTRY.items():
        if not TimeKeeper.query.filter_by(name=parser.name).first():
            db.session.add(TimeKeeper(name=parser.name, parser_module=key, description=parser.description))
    db.session.commit()


def _seed_admin():
    """Create default admin account if no users exist."""
    if User.query.count() == 0:
        admin = User(username="admin", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
