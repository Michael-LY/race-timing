import os
import time
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, current_app, session as flask_session)
from werkzeug.utils import secure_filename
from models import db, Event, Session, LapRecord, Standing, TimeKeeper, User, CarConfig, CarModelColor
from parsers import get_parser, list_parsers
from datetime import datetime

bp = Blueprint("main", __name__)

ALLOWED_EXTENSIONS = {"csv", "txt"}

# Simple in-memory cache for analytics API
# Key: session_id, Value: (timestamp, data)
_analytics_cache: dict[int, tuple[float, dict]] = {}
_ANALYTICS_CACHE_TTL = 300  # 5 minutes
_ANALYTICS_CACHE_MAX = 50

# Chart color palette (must match static/js/charts.js COLORS array order)
CHART_COLORS = [
    '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4',
    '#f97316', '#6366f1', '#14b8a6', '#e11d48', '#a855f7', '#0891b2',
    '#dc2626', '#0d9488', '#78716c', '#eab308', '#475569', '#ec4899',
    '#22d3ee', '#fb923c', '#78350f', '#64748b', '#059669', '#84cc16',
]


def model_to_color(model: str) -> str:
    """Hash a car model name into a chart color (replicates JS getModelColor)."""
    if not model:
        return "#64748b"
    h = 0
    for ch in model:
        h = ((h << 5) - h) + ord(ch)
        h &= 0xFFFFFFFF
        if h > 0x7FFFFFFF:
            h -= 0x100000000
        elif h < -0x80000000:
            h += 0x100000000
    idx = abs(h) % len(CHART_COLORS)
    return CHART_COLORS[idx]


def _get_analytics_cache(session_id: int) -> dict | None:
    if session_id in _analytics_cache:
        ts, data = _analytics_cache[session_id]
        if time.time() - ts < _ANALYTICS_CACHE_TTL:
            return data
        del _analytics_cache[session_id]
    return None


def _set_analytics_cache(session_id: int, data: dict) -> None:
    if len(_analytics_cache) >= _ANALYTICS_CACHE_MAX:
        oldest_key = min(_analytics_cache, key=lambda k: _analytics_cache[k][0])
        del _analytics_cache[oldest_key]
    _analytics_cache[session_id] = (time.time(), data)


def _invalidate_analytics_cache(session_id: int) -> None:
    _analytics_cache.pop(session_id, None)


def _invalidate_all_analytics_caches() -> None:
    _analytics_cache.clear()


def _coerce_position(position):
    try:
        return int(position)
    except (TypeError, ValueError):
        return None


def get_classification_filter_options(standings):
    class_names = []
    seen = set()
    for standing in standings:
        class_name = getattr(standing, "class_name", None)
        if class_name is None:
            continue

        normalized = str(class_name).strip()
        if not normalized:
            continue

        key = normalized.casefold()
        if key in seen:
            continue

        seen.add(key)
        class_names.append(normalized)

    class_names.sort(key=lambda name: name.casefold())
    return class_names


def sort_standings_for_display(standings):
    classified = []
    nc = []
    for standing in standings:
        position = _coerce_position(getattr(standing, "position", None))
        is_classified = bool(getattr(standing, "is_classified", True))
        display_classified = is_classified and position is not None and position > 0
        if display_classified:
            classified.append(standing)
        else:
            nc.append(standing)

    classified.sort(key=lambda s: (
        _coerce_position(getattr(s, "position", None)) or 999999,
        str(getattr(s, "car_number", "") or ""),
    ))
    nc.sort(key=lambda s: (
        -(getattr(s, "laps_completed") or 0),
        str(getattr(s, "car_number", "") or ""),
    ))
    return classified + nc


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------
def login_required(f):
    """Redirect to login page if user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not flask_session.get("user_id"):
            flash("Please log in to continue", "warning")
            return redirect(url_for("main.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Return 403 if user is not an admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            flash("Please log in to continue", "warning")
            return redirect(url_for("main.login", next=request.url))
        user = db.session.get(User, user_id)
        if not user or not user.is_admin:
            flash("Admin access required", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if flask_session.get("user_id"):
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            flask_session["user_id"] = user.id
            flash(f"Welcome back, {user.username}!", "success")
            next_url = request.args.get("next") or url_for("main.index")
            return redirect(next_url)
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    flask_session.pop("user_id", None)
    flash("Logged out", "success")
    return redirect(url_for("main.index"))


@bp.route("/register", methods=["GET", "POST"])
@login_required
@admin_required
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        is_admin = request.form.get("is_admin") == "on"

        if not username or not password:
            flash("Username and password are required", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters", "danger")
        elif password != confirm:
            flash("Passwords do not match", "danger")
        elif User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
        else:
            user = User(username=username, is_admin=is_admin)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f'User "{username}" created', "success")
            return redirect(url_for("main.user_list"))

    return render_template("register.html")


# ---------------------------------------------------------------------------
# User management (admin)
# ---------------------------------------------------------------------------
@bp.route("/users")
@login_required
@admin_required
def user_list():
    """List all users."""
    users = User.query.order_by(User.created_at).all()
    return render_template("users.html", users=users)


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def user_edit(user_id):
    """Edit username and admin flag."""
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        is_admin = request.form.get("is_admin") == "on"

        if not username:
            flash("Username is required", "danger")
        elif username != user.username and User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
        else:
            user.username = username
            user.is_admin = is_admin
            db.session.commit()
            flash(f'User "{username}" updated', "success")
            return redirect(url_for("main.user_list"))

    return render_template("user_edit.html", user=user)


@bp.route("/users/<int:user_id>/password", methods=["GET", "POST"])
@login_required
def user_password(user_id):
    """Change password. Admins can change any user's password; regular users
    can only change their own."""
    user = User.query.get_or_404(user_id)
    current_user_id = flask_session.get("user_id")
    current_user_obj = db.session.get(User, current_user_id) if current_user_id else None

    # Only allow if admin or the user themselves
    if not current_user_obj or (current_user_obj.id != user.id and not current_user_obj.is_admin):
        flash("You don't have permission to change this password", "danger")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not password:
            flash("Password is required", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters", "danger")
        elif password != confirm:
            flash("Passwords do not match", "danger")
        else:
            user.set_password(password)
            db.session.commit()
            flash(f'Password changed for "{user.username}"', "success")
            return redirect(url_for("main.user_list" if current_user_obj.is_admin else "main.index"))

    return render_template("user_password.html", user=user)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def user_delete(user_id):
    """Delete a user. Cannot delete yourself."""
    user = User.query.get_or_404(user_id)
    current_user_id = flask_session.get("user_id")

    if user.id == current_user_id:
        flash("You cannot delete your own account", "danger")
        return redirect(url_for("main.user_list"))

    name = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{name}" deleted', "success")
    return redirect(url_for("main.user_list"))


# ---------------------------------------------------------------------------
# Global Car Model Colors (admin)
# ---------------------------------------------------------------------------
@bp.route("/car-model-colors", methods=["GET", "POST"])
@admin_required
def car_model_colors():
    """Global admin page to set colors for car models (affects all events)."""
    # Collect all known car models from the database
    known_models: set[str] = set()
    for row in Standing.query.with_entities(Standing.car_model).distinct():
        if row.car_model:
            known_models.add(row.car_model)
    for row in CarConfig.query.with_entities(CarConfig.car_model).distinct():
        if row.car_model:
            known_models.add(row.car_model)
    for row in CarModelColor.query.with_entities(CarModelColor.car_model).distinct():
        if row.car_model:
            known_models.add(row.car_model)

    known_models = sorted(known_models, key=str.casefold)

    if request.method == "POST":
        models = request.form.getlist("car_model[]")
        colors = request.form.getlist("model_color[]")
        saved = 0
        for i, model in enumerate(models):
            model = model.strip()
            if not model:
                continue
            color = (colors[i] if i < len(colors) else "").strip()
            entry = CarModelColor.query.filter_by(car_model=model).first()
            if not entry:
                entry = CarModelColor(car_model=model)
                db.session.add(entry)
            entry.model_color = color
            saved += 1
        db.session.commit()
        _invalidate_all_analytics_caches()
        flash(f"Saved {saved} model color(s)", "success")
        return redirect(url_for("main.car_model_colors"))

    # Build model list with existing colors
    models_data = []
    for model in known_models:
        entry = CarModelColor.query.filter_by(car_model=model).first()
        models_data.append({
            "car_model": model,
            "model_color": entry.model_color if entry else "",
        })

    return render_template("car_model_colors.html", models=models_data)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@bp.route("/")
def index():
    query = Event.query

    user_id = flask_session.get("user_id")
    current_user_obj = db.session.get(User, user_id) if user_id else None
    if not current_user_obj or not current_user_obj.is_admin:
        query = query.filter(Event.is_hidden == False)

    year = request.args.get("year", "").strip()
    championship = request.args.get("championship", "").strip()
    track = request.args.get("track", "").strip()
    sort_dir = request.args.get("sort", "desc")

    if year:
        try:
            query = query.filter(Event.year == int(year))
        except ValueError:
            pass
    if championship:
        query = query.filter(Event.championship == championship)
    if track:
        query = query.filter(Event.track == track)

    if sort_dir == "asc":
        events = query.order_by(Event.event_date.asc().nullslast()).all()
    else:
        events = query.order_by(Event.event_date.desc().nullslast()).all()

    all_events = Event.query.all()
    years = sorted({e.year for e in all_events if e.year}, reverse=True)
    championships = sorted({e.championship for e in all_events if e.championship})
    tracks = sorted({e.track for e in all_events if e.track})

    return render_template("index.html", events=events,
                           years=years, championships=championships, tracks=tracks,
                           selected_year=year, selected_championship=championship,
                           selected_track=track, sort_dir=sort_dir)


# ---------------------------------------------------------------------------
# Create event
# ---------------------------------------------------------------------------
@bp.route("/events/new", methods=["GET", "POST"])
@admin_required
def event_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        track = request.form.get("track", "").strip()
        year_str = request.form.get("year", "").strip()
        championship = request.form.get("championship", "").strip()
        date_str = request.form.get("event_date", "").strip()

        if not name:
            flash("Event name is required", "danger")
            return redirect(url_for("main.event_create"))

        event = Event(name=name, track=track, championship=championship)
        if year_str:
            try:
                event.year = int(year_str)
            except ValueError:
                pass
        if date_str:
            try:
                event.event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        db.session.add(event)
        db.session.commit()
        flash(f'Event "{event.name}" created', "success")
        return redirect(url_for("main.event_detail", event_id=event.id))

    return render_template("event_create.html")


# ---------------------------------------------------------------------------
# Event detail
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>")
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)
    if event.is_hidden:
        user_id = flask_session.get("user_id")
        current_user_obj = db.session.get(User, user_id) if user_id else None
        if not current_user_obj or not current_user_obj.is_admin:
            flash("Event not found", "warning")
            return redirect(url_for("main.index"))
    return render_template("event_detail.html", event=event)


@bp.route("/events/<int:event_id>/sessions/reorder", methods=["POST"])
@admin_required
def reorder_event_sessions(event_id):
    event = Event.query.get_or_404(event_id)
    raw_ids = request.form.getlist("session_ids")
    session_ids = []
    for value in raw_ids:
        session_ids.extend([item.strip() for item in value.split(",") if item.strip()])

    if not session_ids:
        flash("No session order was provided", "danger")
        return redirect(url_for("main.event_detail", event_id=event_id))

    sessions = Session.query.filter(Session.event_id == event.id, Session.id.in_([int(sid) for sid in session_ids])).all()
    session_lookup = {session.id: session for session in sessions}

    if len(session_lookup) != len(session_ids):
        flash("Unable to reorder sessions", "danger")
        return redirect(url_for("main.event_detail", event_id=event_id))

    for index, session_id in enumerate(session_ids):
        session = session_lookup.get(int(session_id))
        if session is not None:
            session.sort_order = index

    db.session.commit()
    flash("Sessions reordered", "success")
    return redirect(url_for("main.event_detail", event_id=event_id))


# ---------------------------------------------------------------------------
# Delete event
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>/delete", methods=["POST"])
@admin_required
def event_delete(event_id):
    event = Event.query.get_or_404(event_id)
    name = event.name
    db.session.delete(event)
    db.session.commit()
    flash(f'Event "{name}" deleted', "success")
    return redirect(url_for("main.index"))


# ---------------------------------------------------------------------------
# Edit event
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@admin_required
def event_edit(event_id):
    event = Event.query.get_or_404(event_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        track = request.form.get("track", "").strip()
        year_str = request.form.get("year", "").strip()
        championship = request.form.get("championship", "").strip()
        date_str = request.form.get("event_date", "").strip()

        if not name:
            flash("Event name is required", "danger")
            return redirect(url_for("main.event_edit", event_id=event_id))

        event.name = name
        event.track = track
        event.championship = championship
        event.is_hidden = request.form.get("is_hidden") == "on"
        if year_str:
            try:
                event.year = int(year_str)
            except ValueError:
                pass
        else:
            event.year = None
        if date_str:
            try:
                event.event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            event.event_date = None

        db.session.commit()
        flash(f'Event "{event.name}" updated', "success")
        return redirect(url_for("main.event_detail", event_id=event.id))

    return render_template("event_edit.html", event=event)


# ---------------------------------------------------------------------------
# Upload CSV(s)
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>/upload", methods=["GET", "POST"])
@admin_required
def upload(event_id):
    event = Event.query.get_or_404(event_id)
    parsers = list_parsers()
    selected_parser = request.form.get(
        "parser", event.time_keeper.parser_module if event.time_keeper else ""
    )

    if request.method == "POST":
        parser_key = request.form.get("parser", "")
        parser = get_parser(parser_key)
        if not parser:
            flash("Please select a valid time keeper format", "danger")
            return redirect(url_for("main.upload", event_id=event_id))

        cls_file = request.files.get("classification_file")
        sec_file = request.files.get("sector_file")
        pit_file = request.files.get("pitstops_file")
        tlw_file = request.files.get("tlw_file")
        msg_file = request.files.get("messages_file")

        # Check at least one file uploaded
        any_file = cls_file or sec_file or pit_file or tlw_file or msg_file
        if not any_file:
            flash("Please upload at least one CSV file", "danger")
            return redirect(url_for("main.upload", event_id=event_id))

        # Validate that uploaded files are CSVs
        all_files = [cls_file, sec_file, pit_file, tlw_file, msg_file]
        for f in all_files:
            if f and f.filename and not allowed_file(f.filename):
                flash(f"'{f.filename}' is not a CSV file", "danger")
                return redirect(url_for("main.upload", event_id=event_id))

        # Save files
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")

        def save_file(uploaded_file, prefix):
            if uploaded_file and uploaded_file.filename:
                name = secure_filename(uploaded_file.filename)
                path = os.path.join(
                    current_app.config["UPLOAD_FOLDER"], f"{ts}_{prefix}_{name}"
                )
                uploaded_file.save(path)
                return path
            return None

        cls_path = save_file(cls_file, "cls")
        sec_path = save_file(sec_file, "sec")
        pit_path = save_file(pit_file, "pit")
        tlw_path = save_file(tlw_file, "tlw")
        msg_path = save_file(msg_file, "msg")

        # Parse — pass all paths; each parser uses the kwargs it needs
        try:
            data = parser.parse(
                sector_path=sec_path,
                classification_path=cls_path,
                pitstops_path=pit_path,
                tlw_path=tlw_path,
                messages_path=msg_path,
            )
        except Exception as e:
            flash(f"Parse error: {e}", "danger")
            return redirect(url_for("main.upload", event_id=event_id))

        # Link time keeper
        tk = TimeKeeper.query.filter_by(parser_module=parser_key).first()
        if tk:
            event.time_keeper_id = tk.id

        # Create session — use custom name/type if provided, otherwise parser default
        custom_name = request.form.get("session_name", "").strip()
        custom_type = request.form.get("session_type", "").strip()
        max_sort_order = Session.query.filter_by(event_id=event.id).with_entities(db.func.max(Session.sort_order)).scalar() or 0
        session = Session(
            event_id=event.id,
            name=custom_name if custom_name else data.get("session_name", "Untitled"),
            session_type=custom_type if custom_type else data.get("session_type", "Practice"),
            start_time=datetime.utcnow(),
            sort_order=max_sort_order + 1,
        )
        db.session.add(session)
        db.session.flush()

        # --- Fallback: find car_model from same championship + year ---
        fallback_models: dict[str, str] = {}
        if event.championship and event.year:
            sibling_events = Event.query.filter(
                Event.id != event.id,
                Event.championship == event.championship,
                Event.year == event.year,
            ).all()
            sibling_event_ids = [e.id for e in sibling_events]
            if sibling_event_ids:
                sibling_session_ids = [
                    row[0] for row in Session.query.with_entities(Session.id).filter(
                        Session.event_id.in_(sibling_event_ids)
                    ).all()
                ]
                # From CarConfig
                for cc in CarConfig.query.filter(CarConfig.event_id.in_(sibling_event_ids)):
                    if cc.car_model and cc.car_number not in fallback_models:
                        fallback_models[cc.car_number] = cc.car_model
                # From Standing (latest per car_number)
                if sibling_session_ids:
                    for st in Standing.query.filter(
                        Standing.session_id.in_(sibling_session_ids),
                        Standing.car_model != "",
                        Standing.car_model.isnot(None),
                    ).order_by(Standing.id.desc()).all():
                        if st.car_number not in fallback_models:
                            fallback_models[st.car_number] = st.car_model

        # Insert standings (from Classification)
        car_model_map: dict[str, str] = {}
        for s in data.get("standings", []):
            cm = s.get("car_model", "") or ""
            if not cm:
                cm = fallback_models.get(str(s.get("car_number", "")), "")
            if cm:
                car_model_map[str(s.get("car_number", ""))] = cm
            standing = Standing(
                session_id=session.id,
                position=s.get("position", 0),
                car_number=s.get("car_number", ""),
                team_name=s.get("team_name", ""),
                class_name=s.get("class_name", ""),
                nationality=s.get("nationality", ""),
                car_model=cm,
                model_color=model_to_color(cm),
                total_time=s.get("total_time"),
                gap=s.get("gap"),
                gap_text=s.get("gap_text", "") or "",
                diff=s.get("diff"),
                diff_text=s.get("diff_text", "") or "",
                laps_completed=s.get("laps_completed"),
                fastest_lap=s.get("fastest_lap"),
                fastest_lap_no=s.get("fastest_lap_no"),
                fastest_lap_speed=s.get("fastest_lap_speed"),
                pit_stops=s.get("pit_stops", 0),
                is_classified=s.get("is_classified", True),
            )
            db.session.add(standing)

        # Insert laps (from Sector Analysis)
        laps_data = data.get("laps", [])
        # Mark best laps per car (exclude track_limit, out_lap, in_lap)
        best_times: dict[str, float] = {}
        for l in laps_data:
            if l.get("lap_time") and l["lap_time"] > 0 and not l.get("track_limit") and not l.get("out_lap") and not l.get("in_lap"):
                key = l["car_number"]
                if key not in best_times or l["lap_time"] < best_times[key]:
                    best_times[key] = l["lap_time"]

        for l in laps_data:
            is_best = False
            if l.get("lap_time") and l["lap_time"] > 0 and not l.get("track_limit") and not l.get("out_lap") and not l.get("in_lap"):
                key = l["car_number"]
                if key in best_times and l["lap_time"] == best_times[key]:
                    is_best = True

            lap_cm = l.get("car_model", "") or ""
            if not lap_cm:
                lap_cm = car_model_map.get(str(l.get("car_number", "")), "")

            lap = LapRecord(
                session_id=session.id,
                car_number=l.get("car_number", ""),
                driver_name=l.get("driver_name", ""),
                category=l.get("category", ""),
                car_model=lap_cm,
                model_color=model_to_color(lap_cm),
                lap_number=l.get("lap_number", 0),
                lap_time=l.get("lap_time"),
                sector_1=l.get("sector_1"),
                sector_2=l.get("sector_2"),
                sector_3=l.get("sector_3"),
                gap=l.get("gap"),
                speed=l.get("speed"),
                speed_trap_1=l.get("speed_trap_1"),
                speed_trap_2=l.get("speed_trap_2"),
                speed_trap_3=l.get("speed_trap_3"),
                speed_trap_4=l.get("speed_trap_4"),
                position=l.get("position"),
                is_best=is_best,
                out_lap=l.get("out_lap", False),
                in_lap=l.get("in_lap", False),
                track_limit=l.get("track_limit", False),
                time_out_lap=l.get("time_out_lap"),
                time_in_lap=l.get("time_in_lap"),
                time_of_day=l.get("time_of_day", ""),
                session_time=l.get("session_time"),
            )
            db.session.add(lap)

        db.session.commit()

        n_laps = len(laps_data)
        n_standings = len(data.get("standings", []))
        msg = f'Session "{session.name}" imported: {n_standings} standings, {n_laps} laps'
        flash(msg, "success")
        return redirect(url_for("main.session_detail", session_id=session.id))

    return render_template("upload.html", event=event, parsers=parsers, selected_parser=selected_parser, session_types=SESSION_TYPES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _calculate_pit_stop_time(in_lap, out_lap):
    """Calculate pit-stop duration from TSL timing timestamps when available."""
    in_time = getattr(in_lap, "time_in_lap", None)
    out_time = getattr(out_lap, "time_out_lap", None)

    if in_time is None or out_time is None:
        return None

    try:
        return abs(float(out_time) - float(in_time))
    except (TypeError, ValueError):
        return None


def _best_sectors(valid_laps):
    """Compute best S1/S2/S3 and best lap from a list of valid laps.

    Out laps are excluded from S1 best and fastest lap.
    In laps are excluded from S3 best and fastest lap.
    Returns (best_lap, best_s1_lap, best_s2_lap, best_s3_lap) or None for each.
    """
    clean = [l for l in valid_laps if not l.out_lap and not l.in_lap]
    best_lap = min(clean, key=lambda l: l.lap_time) if clean else None
    best_s1_lap = min((l for l in valid_laps if l.sector_1 and l.sector_1 > 0 and not l.out_lap), key=lambda l: l.sector_1, default=None)
    best_s2_lap = min((l for l in valid_laps if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
    best_s3_lap = min((l for l in valid_laps if l.sector_3 and l.sector_3 > 0 and not l.in_lap), key=lambda l: l.sector_3, default=None)
    return best_lap, best_s1_lap, best_s2_lap, best_s3_lap


def _compute_session_stats(laps: list[LapRecord]):
    """Compute overall and per-car bests across all sectors."""
    valid = [l for l in laps if l.lap_time and l.lap_time > 0 and not l.track_limit]

    best_lap, best_s1_lap, best_s2_lap, best_s3_lap = _best_sectors(valid)

    overall = {
        "lap_time": best_lap.lap_time if best_lap else None,
        "lap_car": best_lap.car_number if best_lap else "",
        "s1": best_s1_lap.sector_1 if best_s1_lap else None,
        "s1_car": best_s1_lap.car_number if best_s1_lap else "",
        "s2": best_s2_lap.sector_2 if best_s2_lap else None,
        "s2_car": best_s2_lap.car_number if best_s2_lap else "",
        "s3": best_s3_lap.sector_3 if best_s3_lap else None,
        "s3_car": best_s3_lap.car_number if best_s3_lap else "",
    }

    # Per-car best S1/S2/S3 (independent of best lap)
    per_car_bests: dict[str, dict] = {}
    car_groups: dict[str, list[LapRecord]] = {}
    for l in laps:
        car_groups.setdefault(l.car_number, []).append(l)

    for car_num, car_laps in car_groups.items():
        cv = [l for l in car_laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
        per_car_bests[car_num] = {
            "s1": min((l.sector_1 for l in cv if l.sector_1 and l.sector_1 > 0 and not l.out_lap), default=None),
            "s2": min((l.sector_2 for l in cv if l.sector_2 and l.sector_2 > 0), default=None),
            "s3": min((l.sector_3 for l in cv if l.sector_3 and l.sector_3 > 0 and not l.in_lap), default=None),
        }

    # Per-stint bests (stint = consecutive laps between pit stops / driver changes)
    stint_bests: dict[int, dict] = {}
    for car_num, car_laps in car_groups.items():
        stints: list[list[LapRecord]] = []
        current: list[LapRecord] = []
        for l in sorted(car_laps, key=lambda x: x.lap_number):
            if l.out_lap and current:
                stints.append(current)
                current = []
            current.append(l)
        if current:
            stints.append(current)

        for stint in stints:
            valid_stint = [l for l in stint if l.lap_time and l.lap_time > 0 and not l.track_limit]
            if not valid_stint:
                continue
            clean_stint = [l for l in valid_stint if not l.out_lap and not l.in_lap]
            best_lap = min(clean_stint, key=lambda l: l.lap_time) if clean_stint else min(valid_stint, key=lambda l: l.lap_time)
            best_s1  = min((l for l in valid_stint if l.sector_1 and l.sector_1 > 0 and not l.out_lap), key=lambda l: l.sector_1, default=None)
            best_s2  = min((l for l in valid_stint if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
            best_s3  = min((l for l in valid_stint if l.sector_3 and l.sector_3 > 0 and not l.in_lap), key=lambda l: l.sector_3, default=None)

            for l in valid_stint:
                flags = stint_bests.setdefault(l.id, {})
                flags["lap"] = l.id == best_lap.id
                flags["s1"] = best_s1 and l.id == best_s1.id
                flags["s2"] = best_s2 and l.id == best_s2.id
                flags["s3"] = best_s3 and l.id == best_s3.id

    return overall, per_car_bests, car_groups, stint_bests


# ---------------------------------------------------------------------------
# Driver analysis helper
# ---------------------------------------------------------------------------
def _compute_driver_analysis(laps):
    """Compute per-driver stats and overall sector bests from a list of laps."""
    driver_groups: dict[str, list[LapRecord]] = {}
    for l in laps:
        name = l.driver_name.strip() if l.driver_name else "Unknown"
        driver_groups.setdefault(name, []).append(l)

    drivers = []
    for name, d_laps in driver_groups.items():
        valid = [l for l in d_laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
        best_lap, best_s1_lap, best_s2_lap, best_s3_lap = _best_sectors(valid)
        best_s1 = best_s1_lap.sector_1 if best_s1_lap else None
        best_s2 = best_s2_lap.sector_2 if best_s2_lap else None
        best_s3 = best_s3_lap.sector_3 if best_s3_lap else None
        theoretical = (best_s1 + best_s2 + best_s3) if (best_s1 and best_s2 and best_s3) else None
        drivers.append({
            "driver_name": name,
            "car_number": d_laps[0].car_number if d_laps else "",
            "total_laps": len(valid),
            "best_lap": best_lap.lap_time if best_lap else None,
            "best_s1": best_s1,
            "best_s2": best_s2,
            "best_s3": best_s3,
            "theoretical": theoretical,
        })
    drivers.sort(key=lambda d: d["best_lap"] if d["best_lap"] else 99999)

    all_valid = [l for l in laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
    _, overall_best_s1_lap, overall_best_s2_lap, overall_best_s3_lap = _best_sectors(all_valid)
    overall_s1 = overall_best_s1_lap.sector_1 if overall_best_s1_lap else None
    overall_s2 = overall_best_s2_lap.sector_2 if overall_best_s2_lap else None
    overall_s3 = overall_best_s3_lap.sector_3 if overall_best_s3_lap else None

    return drivers, overall_s1, overall_s2, overall_s3


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------
@bp.route("/sessions/<int:session_id>")
def session_detail(session_id):
    session = Session.query.get_or_404(session_id)
    standings = sort_standings_for_display(session.standings)
    class_options = get_classification_filter_options(standings)
    laps = session.laps

    overall, per_car_bests, car_groups, stint_bests = _compute_session_stats(laps)

    # Per-car summary
    car_summaries = []
    for car_num, car_laps in car_groups.items():
        valid = [l for l in car_laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
        clean = [l for l in valid if not l.out_lap and not l.in_lap]
        best_lap = min(clean, key=lambda x: x.lap_time) if clean else (min(valid, key=lambda x: x.lap_time) if valid else None)
        drivers_list = list(dict.fromkeys(l.driver_name for l in car_laps if l.driver_name))
        pcb = per_car_bests.get(car_num, {})
        s1 = pcb.get("s1")
        s2 = pcb.get("s2")
        s3 = pcb.get("s3")
        theoretical = (s1 + s2 + s3) if (s1 and s2 and s3) else None
        car_summaries.append({
            "car_number": car_num,
            "driver": ", ".join(drivers_list),
            "category": car_laps[0].category if car_laps else "",
            "total_laps": len(car_laps),
            "best_lap": best_lap.lap_time if best_lap else None,
            "sector_1": best_lap.sector_1 if best_lap else None,
            "sector_2": best_lap.sector_2 if best_lap else None,
            "sector_3": best_lap.sector_3 if best_lap else None,
            "best_s1": s1,
            "best_s2": s2,
            "best_s3": s3,
            "theoretical": theoretical,
            "speed": best_lap.speed if best_lap else None,
        })
    car_summaries.sort(key=lambda x: x["best_lap"] if x["best_lap"] else 99999)

    overall_best_theoretical = min((c["theoretical"] for c in car_summaries if c["theoretical"]), default=None)

    drivers, driver_overall_s1, driver_overall_s2, driver_overall_s3 = _compute_driver_analysis(laps)

    # Compute car colors for table row backgrounds (matches analytics API logic)
    car_colors: dict[str, str] = {}
    car_model_map: dict[str, str] = {}
    for s in session.standings:
        cn = str(s.car_number)
        if s.car_model:
            car_model_map[cn] = s.car_model
        car_colors[cn] = s.model_color or ""
    # Global CarModelColor overrides
    global_model_colors: dict[str, str] = {}
    for g in CarModelColor.query.all():
        if g.model_color:
            global_model_colors[g.car_model] = g.model_color
    for cn, cm in car_model_map.items():
        if cm in global_model_colors:
            car_colors[cn] = global_model_colors[cm]
    # Fallback to hash for any car still empty
    for s in session.standings:
        cn = str(s.car_number)
        if not car_colors.get(cn):
            car_colors[cn] = model_to_color(car_model_map.get(cn, ""))

    return render_template("session_detail.html",
                           session=session,
                           standings=standings,
                           class_options=class_options,
                           car_summaries=car_summaries,
                           car_groups=car_groups,
                           overall=overall,
                           per_car_bests=per_car_bests,
                           drivers=drivers,
                           driver_overall_s1=driver_overall_s1,
                           driver_overall_s2=driver_overall_s2,
                           driver_overall_s3=driver_overall_s3,
                           stint_bests=stint_bests,
                           overall_best_theoretical=overall_best_theoretical,
                           car_colors=car_colors)


# ---------------------------------------------------------------------------
# Driver Analysis
# ---------------------------------------------------------------------------
@bp.route("/sessions/<int:session_id>/drivers")
def driver_analysis(session_id):
    session = Session.query.get_or_404(session_id)
    laps = session.laps

    drivers, overall_best_s1, overall_best_s2, overall_best_s3 = _compute_driver_analysis(laps)

    return render_template("driver_analysis.html",
                           session=session,
                           drivers=drivers,
                           overall_best_s1=overall_best_s1,
                           overall_best_s2=overall_best_s2,
                           overall_best_s3=overall_best_s3)


# ---------------------------------------------------------------------------
# Delete session
# ---------------------------------------------------------------------------
@bp.route("/sessions/<int:session_id>/delete", methods=["POST"])
@admin_required
def session_delete(session_id):
    session = Session.query.get_or_404(session_id)
    event_id = session.event_id
    name = session.name
    _invalidate_analytics_cache(session_id)
    db.session.delete(session)
    db.session.commit()
    flash(f'Session "{name}" deleted', "success")
    return redirect(url_for("main.event_detail", event_id=event_id))


@bp.route("/sessions/<int:session_id>/refresh-flags", methods=["POST"])
@admin_required
def session_refresh_flags(session_id):
    """Mark Lap 1 as out_lap for each car. Preserves existing flags."""
    from parsers.detect_laps import detect_out_laps

    session = Session.query.get_or_404(session_id)
    laps = LapRecord.query.filter_by(session_id=session.id).all()

    laps_dicts = [{"car_number": l.car_number, "lap_number": l.lap_number, "out_lap": l.out_lap} for l in laps]

    detect_out_laps(laps_dicts)

    for l in laps:
        d = next(d for d in laps_dicts if d["car_number"] == l.car_number and d["lap_number"] == l.lap_number)
        l.out_lap = d["out_lap"]

    db.session.commit()
    _invalidate_analytics_cache(session_id)

    flash(f"Marked Lap 1 as out lap for {session.name}", "success")
    return redirect(url_for("main.session_detail", session_id=session.id))


@bp.route("/sessions/<int:session_id>/upload-tlw", methods=["GET", "POST"])
@admin_required
def session_upload_tlw(session_id):
    """Upload TLW file for an existing session to add track_limit data."""
    from parsers.detect_laps import parse_tlw_file, apply_tlw
    from werkzeug.utils import secure_filename

    session = Session.query.get_or_404(session_id)

    if request.method == "POST":
        tlw_file = request.files.get("tlw_file")
        if not tlw_file or not tlw_file.filename:
            flash("Please select a TLW file", "danger")
            return redirect(url_for("main.session_upload_tlw", session_id=session.id))

        # Save uploaded file
        filename = secure_filename(tlw_file.filename)
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        filepath = os.path.join(upload_folder, f"tlw_{session_id}_{filename}")
        tlw_file.save(filepath)

        # Parse TLW
        warnings = parse_tlw_file(filepath)
        if not warnings:
            flash("TLW file is empty or has incorrect format", "danger")
            return redirect(url_for("main.session_upload_tlw", session_id=session.id))

        # Load existing laps
        laps = LapRecord.query.filter_by(session_id=session.id).all()
        laps_dicts = []
        for l in laps:
            laps_dicts.append({
                "car_number": l.car_number,
                "lap_number": l.lap_number,
                "lap_time": l.lap_time,
                "out_lap": l.out_lap,
                "in_lap": l.in_lap,
                "track_limit": False,
                "session_time": l.session_time,
            })

        # Apply TLW
        apply_tlw(laps_dicts, warnings)

        # Write back track_limit
        for l in laps:
            d = next(d for d in laps_dicts if d["car_number"] == l.car_number and d["lap_number"] == l.lap_number)
            l.track_limit = d.get("track_limit", False)

        # Re-compute is_best
        best_times = {}
        for d in laps_dicts:
            if d.get("lap_time") and d["lap_time"] > 0 and not d.get("out_lap") and not d.get("in_lap") and not d.get("track_limit"):
                key = d["car_number"]
                if key not in best_times or d["lap_time"] < best_times[key]:
                    best_times[key] = d["lap_time"]

        for l in laps:
            d = next(d for d in laps_dicts if d["car_number"] == l.car_number and d["lap_number"] == l.lap_number)
            is_best = False
            if l.lap_time and l.lap_time > 0 and not d.get("out_lap") and not d.get("in_lap") and not l.track_limit:
                key = l.car_number
                if key in best_times and l.lap_time == best_times[key]:
                    is_best = True
            l.is_best = is_best

        db.session.commit()
        _invalidate_analytics_cache(session_id)

        n_tl = sum(1 for d in laps_dicts if d.get("track_limit"))
        flash(f'TLW uploaded: matched {n_tl} track limit laps', "success")
        return redirect(url_for("main.session_detail", session_id=session.id))

    return render_template("upload_tlw.html", session=session)


@bp.route("/sessions/<int:session_id>/reupload", methods=["GET", "POST"])
@admin_required
def session_reupload(session_id):
    """Re-upload a CSV file to update existing session data."""
    from werkzeug.utils import secure_filename
    from parsers import get_parser

    session = Session.query.get_or_404(session_id)
    event = session.event
    parser_key = event.time_keeper.parser_module if event.time_keeper else ""

    # Determine available file types based on parser
    if parser_key == "swiss_timing":
        file_types = [
            {"key": "sector", "label": "SectorListCSV (Lap Data)"},
            {"key": "classification", "label": "ResultListCSV (Standings)"},
            {"key": "pitstops", "label": "PitStopsCsv (Pit Stops)"},
            {"key": "tlw", "label": "TLWlistMessage (Track Limits)"},
        ]
    elif parser_key == "tsl_timing":
        file_types = [
            {"key": "sector", "label": "Sector Analysis (Lap Data)"},
            {"key": "classification", "label": "Classification (Standings)"},
        ]
    else:
        flash("No time keeper format assigned to this event", "danger")
        return redirect(url_for("main.session_detail", session_id=session.id))

    if request.method == "POST":
        file_type = request.form.get("file_type", "")
        csv_file = request.files.get("csv_file")

        if not csv_file or not csv_file.filename:
            flash("Please select a CSV file", "danger")
            return redirect(url_for("main.session_reupload", session_id=session.id))

        if not allowed_file(csv_file.filename):
            flash(f"'{csv_file.filename}' is not a CSV file", "danger")
            return redirect(url_for("main.session_reupload", session_id=session.id))

        # Save uploaded file
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = secure_filename(csv_file.filename)
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        filepath = os.path.join(upload_folder, f"{ts}_reupload_{file_type}_{filename}")
        csv_file.save(filepath)

        parser = get_parser(parser_key)
        if not parser:
            flash("Parser not found", "danger")
            return redirect(url_for("main.session_reupload", session_id=session.id))

        try:
            if file_type == "sector":
                _reupload_sector(session, parser, parser_key, filepath)
                flash("Lap data updated successfully", "success")
            elif file_type == "classification":
                _reupload_classification(session, parser, parser_key, filepath)
                flash("Standings updated successfully", "success")
            elif file_type == "pitstops":
                _reupload_pitstops(session, parser, filepath)
                flash("Pit stop data updated successfully", "success")
            elif file_type == "tlw":
                _reupload_tlw(session, filepath)
                flash("Track limit data updated successfully", "success")
            else:
                flash(f"Unknown file type: {file_type}", "danger")
                return redirect(url_for("main.session_reupload", session_id=session.id))
        except Exception as e:
            flash(f"Error processing file: {e}", "danger")
            return redirect(url_for("main.session_reupload", session_id=session.id))

        _invalidate_analytics_cache(session_id)
        return redirect(url_for("main.session_detail", session_id=session.id))

    return render_template("reupload.html", session=session, file_types=file_types)


def _reupload_sector(session, parser, parser_key, filepath):
    """Re-upload sector CSV: replace all lap records."""
    data = parser.parse(sector_path=filepath)
    laps_data = data.get("laps", [])

    # Build car_model map from existing standings
    car_model_map = {}
    for s in session.standings:
        cn = str(s.car_number)
        if s.car_model:
            car_model_map[cn] = s.car_model

    # Delete existing laps
    LapRecord.query.filter_by(session_id=session.id).delete()

    # Compute best times (exclude out_lap, in_lap, track_limit)
    best_times = {}
    for l in laps_data:
        if l.get("lap_time") and l["lap_time"] > 0 and not l.get("out_lap") and not l.get("in_lap") and not l.get("track_limit"):
            key = l["car_number"]
            if key not in best_times or l["lap_time"] < best_times[key]:
                best_times[key] = l["lap_time"]

    # Insert new laps
    for l in laps_data:
        is_best = False
        if l.get("lap_time") and l["lap_time"] > 0 and not l.get("out_lap") and not l.get("in_lap") and not l.get("track_limit"):
            key = l["car_number"]
            if key in best_times and l["lap_time"] == best_times[key]:
                is_best = True

        lap_cm = l.get("car_model", "") or car_model_map.get(str(l.get("car_number", "")), "")

        lap = LapRecord(
            session_id=session.id,
            car_number=l.get("car_number", ""),
            driver_name=l.get("driver_name", ""),
            category=l.get("category", ""),
            car_model=lap_cm,
            model_color=model_to_color(lap_cm),
            lap_number=l.get("lap_number", 0),
            lap_time=l.get("lap_time"),
            sector_1=l.get("sector_1"),
            sector_2=l.get("sector_2"),
            sector_3=l.get("sector_3"),
            gap=l.get("gap"),
            speed=l.get("speed"),
            speed_trap_1=l.get("speed_trap_1"),
            speed_trap_2=l.get("speed_trap_2"),
            speed_trap_3=l.get("speed_trap_3"),
            speed_trap_4=l.get("speed_trap_4"),
            position=l.get("position"),
            is_best=is_best,
            out_lap=l.get("out_lap", False),
            in_lap=l.get("in_lap", False),
            track_limit=l.get("track_limit", False),
            time_out_lap=l.get("time_out_lap"),
            time_in_lap=l.get("time_in_lap"),
            time_of_day=l.get("time_of_day", ""),
            session_time=l.get("session_time"),
        )
        db.session.add(lap)

    db.session.commit()


def _reupload_classification(session, parser, parser_key, filepath):
    """Re-upload classification CSV: replace all standings."""
    if parser_key == "swiss_timing":
        data = parser.parse(sector_path=None, classification_path=filepath)
    else:
        data = parser.parse(classification_path=filepath)

    standings_data = data.get("standings", [])

    # Delete existing standings
    Standing.query.filter_by(session_id=session.id).delete()

    # Insert new standings
    for s in standings_data:
        standing = Standing(
            session_id=session.id,
            position=s.get("position", 0),
            car_number=s.get("car_number", ""),
            team_name=s.get("team_name", ""),
            class_name=s.get("class_name", ""),
            nationality=s.get("nationality", ""),
            total_time=s.get("total_time"),
            gap=s.get("gap"),
            diff=s.get("diff"),
            gap_text=s.get("gap_text", "") or "",
            diff_text=s.get("diff_text", "") or "",
            laps_completed=s.get("laps_completed"),
            fastest_lap=s.get("fastest_lap"),
            fastest_lap_no=s.get("fastest_lap_no"),
            fastest_lap_speed=s.get("fastest_lap_speed"),
            pit_stops=s.get("pit_stops", 0),
            is_classified=s.get("is_classified", True),
            car_model=s.get("car_model", ""),
            model_color=model_to_color(s.get("car_model", "")),
        )
        db.session.add(standing)

    db.session.commit()

    # Update car_model on existing laps from new standings
    car_model_map = {}
    for s in standings_data:
        cn = str(s.get("car_number", ""))
        cm = s.get("car_model", "")
        if cn and cm:
            car_model_map[cn] = cm

    if car_model_map:
        laps = LapRecord.query.filter_by(session_id=session.id).all()
        for l in laps:
            cm = car_model_map.get(l.car_number, "")
            if cm:
                l.car_model = cm
                l.model_color = model_to_color(cm)
        db.session.commit()


def _reupload_pitstops(session, parser, filepath):
    """Re-upload pitstops CSV: update in_lap/out_lap flags on existing laps."""
    pitstops = parser._parse_pitstops(filepath)
    laps = LapRecord.query.filter_by(session_id=session.id).all()

    # Convert to dicts
    laps_dicts = []
    for l in laps:
        laps_dicts.append({
            "car_number": l.car_number,
            "lap_number": l.lap_number,
            "lap_time": l.lap_time,
            "out_lap": False,
            "in_lap": False,
            "track_limit": l.track_limit,
            "session_time": l.session_time,
            "driver_name": l.driver_name,
        })

    # Reset and re-apply
    parser._apply_pitstops(laps_dicts, pitstops)

    # Write back
    for l in laps:
        d = next(d for d in laps_dicts if d["car_number"] == l.car_number and d["lap_number"] == l.lap_number)
        l.out_lap = d["out_lap"]
        l.in_lap = d["in_lap"]

    # Re-compute is_best
    best_times = {}
    for d in laps_dicts:
        if d.get("lap_time") and d["lap_time"] > 0 and not d.get("out_lap") and not d.get("in_lap") and not d.get("track_limit"):
            key = d["car_number"]
            if key not in best_times or d["lap_time"] < best_times[key]:
                best_times[key] = d["lap_time"]

    for l in laps:
        d = next(d for d in laps_dicts if d["car_number"] == l.car_number and d["lap_number"] == l.lap_number)
        is_best = False
        if l.lap_time and l.lap_time > 0 and not d.get("out_lap") and not d.get("in_lap") and not l.track_limit:
            key = l.car_number
            if key in best_times and l.lap_time == best_times[key]:
                is_best = True
        l.is_best = is_best

    db.session.commit()


def _reupload_tlw(session, filepath):
    """Re-upload TLW CSV: update track_limit flags on existing laps."""
    from parsers.detect_laps import parse_tlw_file, apply_tlw

    warnings = parse_tlw_file(filepath)
    if not warnings:
        flash("TLW file is empty or has incorrect format", "danger")
        return

    laps = LapRecord.query.filter_by(session_id=session.id).all()
    laps_dicts = []
    for l in laps:
        laps_dicts.append({
            "car_number": l.car_number,
            "lap_number": l.lap_number,
            "lap_time": l.lap_time,
            "out_lap": l.out_lap,
            "in_lap": l.in_lap,
            "track_limit": False,
            "session_time": l.session_time,
        })

    apply_tlw(laps_dicts, warnings)

    for l in laps:
        d = next(d for d in laps_dicts if d["car_number"] == l.car_number and d["lap_number"] == l.lap_number)
        l.track_limit = d.get("track_limit", False)

    # Re-compute is_best
    best_times = {}
    for d in laps_dicts:
        if d.get("lap_time") and d["lap_time"] > 0 and not d.get("out_lap") and not d.get("in_lap") and not d.get("track_limit"):
            key = d["car_number"]
            if key not in best_times or d["lap_time"] < best_times[key]:
                best_times[key] = d["lap_time"]

    for l in laps:
        d = next(d for d in laps_dicts if d["car_number"] == l.car_number and d["lap_number"] == l.lap_number)
        is_best = False
        if l.lap_time and l.lap_time > 0 and not d.get("out_lap") and not d.get("in_lap") and not l.track_limit:
            key = l.car_number
            if key in best_times and l.lap_time == best_times[key]:
                is_best = True
        l.is_best = is_best

    db.session.commit()


# ---------------------------------------------------------------------------
# Event-level car configuration editor
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>/car-config", methods=["GET", "POST"])
@admin_required
def event_car_config(event_id):
    """Admin page to configure car-level settings (model, color, team, class) per event."""
    from sqlalchemy import distinct

    def _car_chart_color(car_number: str, series_color: str) -> str:
        """Replicate charts.js getCarColor logic for fallback display."""
        if series_color and len(series_color) == 7 and series_color.startswith("#"):
            return series_color
        try:
            idx = int(car_number) % len(CHART_COLORS)
        except (ValueError, TypeError):
            idx = 0
        return CHART_COLORS[idx]
    event = Event.query.get_or_404(event_id)

    # Collect unique car numbers across all sessions in this event
    session_ids = [s.id for s in event.sessions]
    if not session_ids:
        flash("No sessions in this event. Upload data first.", "warning")
        return redirect(url_for("main.event_detail", event_id=event_id))

    if request.method == "POST":
        car_numbers = request.form.getlist("car_number[]")
        car_models = request.form.getlist("car_model[]")
        colors = request.form.getlist("series_color[]")
        teams = request.form.getlist("team_name[]")
        classes = request.form.getlist("class_name[]")

        updated_count = 0
        for i, cn in enumerate(car_numbers):
            cn = cn.strip()
            if not cn:
                continue
            model = (car_models[i] if i < len(car_models) else "").strip()
            color = (colors[i] if i < len(colors) else "").strip()
            team = (teams[i] if i < len(teams) else "").strip()
            cls_ = (classes[i] if i < len(classes) else "").strip()

            # Upsert CarConfig
            cfg = CarConfig.query.filter_by(event_id=event.id, car_number=cn).first()
            if not cfg:
                cfg = CarConfig(event_id=event.id, car_number=cn)
                db.session.add(cfg)
            cfg.car_model = model
            model_color = model_to_color(model)
            cfg.model_color = model_color
            cfg.series_color = color
            cfg.team_name = team
            cfg.class_name = cls_

            # Propagate to all standings in this event
            Standing.query.filter(
                Standing.session_id.in_(session_ids),
                Standing.car_number == cn
            ).update({
                "car_model": model,
                "model_color": model_color,
                "series_color": color,
                "team_name": team,
                "class_name": cls_,
            })

            # Propagate to all lap records in this event
            LapRecord.query.filter(
                LapRecord.session_id.in_(session_ids),
                LapRecord.car_number == cn
            ).update({
                "car_model": model,
                "model_color": model_color,
                "series_color": color,
            })

            updated_count += 1

        db.session.commit()
        # Invalidate analytics caches for all sessions
        for sid in session_ids:
            _invalidate_analytics_cache(sid)

        flash(f"Saved {updated_count} car(s)", "success")
        return redirect(url_for("main.event_car_config", event_id=event_id))

    # GET: gather unique cars from all sessions in the event
    car_numbers: list[str] = []
    seen = set()
    for s in event.sessions:
        for st in s.standings:
            cn = str(st.car_number)
            if cn and cn not in seen:
                seen.add(cn)
                car_numbers.append(cn)
    car_numbers.sort(key=lambda x: (len(x), x))  # numeric-ish sort

    # Build car list with values from CarConfig (fallback to latest Standing)
    cars = []
    for cn in car_numbers:
        cfg = CarConfig.query.filter_by(event_id=event.id, car_number=cn).first()
        if cfg:
            cars.append({
                "car_number": cn,
                "car_model": cfg.car_model,
                "series_color": cfg.series_color,
                "model_color": cfg.model_color or model_to_color(cfg.car_model),
                "effective_color": _car_chart_color(cn, cfg.series_color),
                "team_name": cfg.team_name,
                "class_name": cfg.class_name,
            })
        else:
            # Fallback: get latest standing for this car
            st = Standing.query.filter(
                Standing.session_id.in_(session_ids),
                Standing.car_number == cn
            ).order_by(Standing.id.desc()).first()
            cars.append({
                "car_number": cn,
                "car_model": st.car_model if st else "",
                "series_color": st.series_color if st else "",
                "model_color": (st.model_color if st else "") or model_to_color(st.car_model if st else ""),
                "effective_color": _car_chart_color(cn, st.series_color if st else ""),
                "team_name": st.team_name if st else "",
                "class_name": st.class_name if st else "",
            })

    # Collect class and team options from standings for dropdown hints
    class_options = sorted(set(
        st.class_name for s in event.sessions for st in s.standings if st.class_name
    ))
    team_options = sorted(set(
        st.team_name for s in event.sessions for st in s.standings if st.team_name
    ))

    # Collect all car_model values from the entire database for autocomplete
    db_models: set[str] = set()
    for row in Standing.query.with_entities(Standing.car_model).distinct():
        if row.car_model:
            db_models.add(row.car_model)
    for row in CarConfig.query.with_entities(CarConfig.car_model).distinct():
        if row.car_model:
            db_models.add(row.car_model)
    car_model_options = sorted(db_models, key=str.casefold)

    return render_template("event_car_config.html", event=event, cars=cars,
                           class_options=class_options, team_options=team_options,
                           car_model_options=car_model_options)


# ---------------------------------------------------------------------------
# API — batch update car models
# ---------------------------------------------------------------------------
@bp.route("/api/sessions/<int:session_id>/car-models", methods=["POST"])
@admin_required
def api_update_car_models(session_id):
    """Batch update car models for a session.
    JSON body: { "models": { "car_number": "model_name", ... } }
    Updates both Standing and LapRecord.
    """
    session = Session.query.get_or_404(session_id)
    data = request.get_json(silent=True)
    if not data or "models" not in data:
        return jsonify({"ok": False, "error": "Missing 'models'"}), 400
    models = data["models"]
    updated = 0
    for car_num, model in models.items():
        model = (model or "").strip()
        cnt = Standing.query.filter_by(session_id=session.id, car_number=str(car_num)).update({"car_model": model})
        cnt += LapRecord.query.filter_by(session_id=session.id, car_number=str(car_num)).update({"car_model": model})
        if cnt > 0:
            updated += 1
    db.session.commit()
    _invalidate_analytics_cache(session_id)
    return jsonify({"ok": True, "updated_cars": updated})


# ---------------------------------------------------------------------------
# Edit session
# ---------------------------------------------------------------------------
SESSION_TYPES = ["Paid-Test", "Practice", "Bronze-Session", "Pre-Qualifying", "Qualifying", "Warm-up", "Race"]
SESSION_TYPE_ALIASES = {
    "Paid Test": "Paid-Test",
    "Bronze Session": "Bronze-Session",
}


def normalize_session_type(session_type: str | None) -> str | None:
    if not session_type:
        return session_type
    return SESSION_TYPE_ALIASES.get(session_type, session_type)


@bp.route("/sessions/<int:session_id>/edit", methods=["GET", "POST"])
@admin_required
def session_edit(session_id):
    session = Session.query.get_or_404(session_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        session_type = normalize_session_type(request.form.get("session_type", "").strip())

        if not name:
            flash("Session name is required", "danger")
            return redirect(url_for("main.session_edit", session_id=session_id))
        if session_type not in SESSION_TYPES:
            flash("Invalid session type", "danger")
            return redirect(url_for("main.session_edit", session_id=session_id))

        session.name = name
        session.session_type = session_type
        db.session.commit()
        flash(f'Session "{session.name}" updated', "success")
        return redirect(url_for("main.event_detail", event_id=session.event_id))

    return render_template("session_edit.html", session=session, session_types=SESSION_TYPES)


# ---------------------------------------------------------------------------
# API — lazy-loaded table data
# ---------------------------------------------------------------------------

@bp.route("/api/sessions/<int:session_id>/laps")
def api_session_laps(session_id):
    """Return lap data for lazy-loading the lap-by-lap table."""
    session = Session.query.get_or_404(session_id)
    laps = session.laps

    car_filter = request.args.get("car", "").strip()

    # Group by car
    car_groups: dict[str, list[LapRecord]] = {}
    for l in laps:
        car_groups.setdefault(l.car_number, []).append(l)

    # Compute per-car bests (for highlighting)
    per_car_bests = {}
    for car_num, car_laps in car_groups.items():
        cv = [l for l in car_laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
        per_car_bests[car_num] = {
            "s1": min((l.sector_1 for l in cv if l.sector_1 and l.sector_1 > 0 and not l.out_lap), default=None),
            "s2": min((l.sector_2 for l in cv if l.sector_2 and l.sector_2 > 0), default=None),
            "s3": min((l.sector_3 for l in cv if l.sector_3 and l.sector_3 > 0 and not l.in_lap), default=None),
        }

    # Compute stint bests
    stint_bests = {}
    for car_num, car_laps in car_groups.items():
        stints = []
        current = []
        for l in sorted(car_laps, key=lambda x: x.lap_number):
            if l.out_lap and current:
                stints.append(current)
                current = []
            current.append(l)
        if current:
            stints.append(current)

        for stint in stints:
            valid_stint = [l for l in stint if l.lap_time and l.lap_time > 0 and not l.track_limit]
            if not valid_stint:
                continue
            clean_stint = [l for l in valid_stint if not l.out_lap and not l.in_lap]
            best_lap = min(clean_stint, key=lambda l: l.lap_time) if clean_stint else min(valid_stint, key=lambda l: l.lap_time)
            best_s1 = min((l for l in valid_stint if l.sector_1 and l.sector_1 > 0 and not l.out_lap), key=lambda l: l.sector_1, default=None)
            best_s2 = min((l for l in valid_stint if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
            best_s3 = min((l for l in valid_stint if l.sector_3 and l.sector_3 > 0 and not l.in_lap), key=lambda l: l.sector_3, default=None)

            for l in valid_stint:
                flags = stint_bests.setdefault(l.id, {})
                flags["lap"] = l.id == best_lap.id
                flags["s1"] = best_s1 and l.id == best_s1.id
                flags["s2"] = best_s2 and l.id == best_s2.id
                flags["s3"] = best_s3 and l.id == best_s3.id

    # Overall bests
    valid_all = [l for l in laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
    clean_all = [l for l in valid_all if not l.out_lap and not l.in_lap]
    best_lap = min(clean_all, key=lambda l: l.lap_time) if clean_all else None
    best_s1_lap = min((l for l in valid_all if l.sector_1 and l.sector_1 > 0 and not l.out_lap), key=lambda l: l.sector_1, default=None)
    best_s2_lap = min((l for l in valid_all if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
    best_s3_lap = min((l for l in valid_all if l.sector_3 and l.sector_3 > 0 and not l.in_lap), key=lambda l: l.sector_3, default=None)
    overall = {
        "lap_time": best_lap.lap_time if best_lap else None,
        "lap_car": best_lap.car_number if best_lap else "",
        "s1": best_s1_lap.sector_1 if best_s1_lap else None,
        "s1_car": best_s1_lap.car_number if best_s1_lap else "",
        "s2": best_s2_lap.sector_2 if best_s2_lap else None,
        "s2_car": best_s2_lap.car_number if best_s2_lap else "",
        "s3": best_s3_lap.sector_3 if best_s3_lap else None,
        "s3_car": best_s3_lap.car_number if best_s3_lap else "",
    }

    # Build lap data
    result_laps = []
    for car_num in sorted(car_groups.keys()):
        if car_filter and car_num != car_filter:
            continue
        for l in sorted(car_groups[car_num], key=lambda x: x.lap_number):
            result_laps.append({
                "id": l.id,
                "car_number": l.car_number,
                "driver_name": l.driver_name,
                "lap_number": l.lap_number,
                "lap_time": l.lap_time,
                "sector_1": l.sector_1,
                "sector_2": l.sector_2,
                "sector_3": l.sector_3,
                "speed_trap_4": l.speed_trap_4,
                "speed": l.speed,
                "out_lap": l.out_lap,
                "in_lap": l.in_lap,
                "track_limit": l.track_limit,
                "is_best": l.is_best,
                "stint_bests": stint_bests.get(l.id, {}),
            })

    return jsonify({
        "laps": result_laps,
        "per_car_bests": per_car_bests,
        "overall": overall,
        "car_groups": {cn: len(cls) for cn, cls in car_groups.items()},
    })


@bp.route("/api/sessions/<int:session_id>/drivers")
def api_session_drivers(session_id):
    """Return driver analysis data for lazy-loading the drivers table."""
    session = Session.query.get_or_404(session_id)
    laps = session.laps

    driver_groups: dict[str, list[LapRecord]] = {}
    for l in laps:
        name = l.driver_name.strip() if l.driver_name else "Unknown"
        driver_groups.setdefault(name, []).append(l)

    drivers = []
    for name, d_laps in driver_groups.items():
        valid = [l for l in d_laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
        clean = [l for l in valid if not l.out_lap and not l.in_lap]
        best_lap = min(clean, key=lambda l: l.lap_time) if clean else None
        best_s1_lap = min((l for l in valid if l.sector_1 and l.sector_1 > 0 and not l.out_lap), key=lambda l: l.sector_1, default=None)
        best_s2_lap = min((l for l in valid if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
        best_s3_lap = min((l for l in valid if l.sector_3 and l.sector_3 > 0 and not l.in_lap), key=lambda l: l.sector_3, default=None)
        best_s1 = best_s1_lap.sector_1 if best_s1_lap else None
        best_s2 = best_s2_lap.sector_2 if best_s2_lap else None
        best_s3 = best_s3_lap.sector_3 if best_s3_lap else None
        theoretical = (best_s1 + best_s2 + best_s3) if (best_s1 and best_s2 and best_s3) else None
        drivers.append({
            "driver_name": name,
            "car_number": d_laps[0].car_number if d_laps else "",
            "total_laps": len(valid),
            "best_lap": best_lap.lap_time if best_lap else None,
            "best_s1": best_s1,
            "best_s2": best_s2,
            "best_s3": best_s3,
            "theoretical": theoretical,
        })
    drivers.sort(key=lambda d: d["best_lap"] if d["best_lap"] else 99999)

    # Overall bests
    all_valid = [l for l in laps if l.lap_time and l.lap_time > 0 and not l.track_limit]
    clean_all = [l for l in all_valid if not l.out_lap and not l.in_lap]
    _, overall_best_s1_lap, overall_best_s2_lap, overall_best_s3_lap = _best_sectors(all_valid) if all_valid else (None, None, None, None)
    overall_s1 = overall_best_s1_lap.sector_1 if overall_best_s1_lap else None
    overall_s2 = overall_best_s2_lap.sector_2 if overall_best_s2_lap else None
    overall_s3 = overall_best_s3_lap.sector_3 if overall_best_s3_lap else None

    return jsonify({
        "drivers": drivers,
        "overall_s1": overall_s1,
        "overall_s2": overall_s2,
        "overall_s3": overall_s3,
    })


# ---------------------------------------------------------------------------
# API — analytics data for charts
# ---------------------------------------------------------------------------
# Safety car lap detection threshold: lap_time > median_clean * SC_THRESHOLD → flagged as SC
SC_THRESHOLD = 1.35


@bp.route("/api/sessions/<int:session_id>/analytics")
def api_session_analytics(session_id):
    cached = _get_analytics_cache(session_id)
    if cached is not None:
        return jsonify(cached)

    session = Session.query.get_or_404(session_id)
    laps = session.laps

    # Group by car
    car_groups: dict[str, list[LapRecord]] = {}
    for l in laps:
        car_groups.setdefault(l.car_number, []).append(l)

    # Pre-compute per-car median clean lap time for SC detection
    car_median_clean: dict[str, float] = {}
    for car_num, car_laps in car_groups.items():
        clean = sorted([
            l.lap_time for l in car_laps
            if l.lap_time and l.lap_time > 0 and not l.out_lap and not l.in_lap and not l.track_limit
        ])
        if clean:
            car_median_clean[car_num] = clean[len(clean) // 2]

    # Build car_model map, series_color map, and model_color map from standings
    car_model_map: dict[str, str] = {}
    car_color_map: dict[str, str] = {}
    car_model_color_map: dict[str, str] = {}
    for s in session.standings:
        cn = str(s.car_number)
        if s.car_model:
            car_model_map[cn] = s.car_model
        if s.series_color:
            car_color_map[cn] = s.series_color
        if s.model_color:
            car_model_color_map[cn] = s.model_color

    # Global CarModelColor overrides — if a global color is set for a car's model,
    # use it instead of the per-row model_color (hash-based)
    global_model_colors: dict[str, str] = {}
    for g in CarModelColor.query.all():
        if g.model_color:
            global_model_colors[g.car_model] = g.model_color
    if global_model_colors:
        for cn, cm in car_model_map.items():
            if cm in global_model_colors:
                car_model_color_map[cn] = global_model_colors[cm]

    # Per-car stats
    per_car = []
    for car_num, car_laps in car_groups.items():
        median = car_median_clean.get(car_num)
        valid = [l for l in car_laps if l.lap_time and l.lap_time > 0
                 and not l.out_lap and not l.in_lap and not l.track_limit
                 and not (median and l.lap_time > median * SC_THRESHOLD)]
        if not valid:
            valid = [l for l in car_laps if l.lap_time and l.lap_time > 0 and not l.track_limit]

        clean_for_lap = [l for l in valid if not l.out_lap and not l.in_lap]
        best_lap = min(clean_for_lap, key=lambda l: l.lap_time) if clean_for_lap else (min(valid, key=lambda l: l.lap_time) if valid else None)
        best_s1 = min((l.sector_1 for l in valid if l.sector_1 and l.sector_1 > 0 and not l.out_lap), default=None)
        best_s2 = min((l.sector_2 for l in valid if l.sector_2 and l.sector_2 > 0), default=None)
        best_s3 = min((l.sector_3 for l in valid if l.sector_3 and l.sector_3 > 0 and not l.in_lap), default=None)
        theoretical = (best_s1 + best_s2 + best_s3) if (best_s1 and best_s2 and best_s3) else None
        top_speed = max((l.speed_trap_4 for l in car_laps if l.speed_trap_4 and l.speed_trap_4 > 0), default=None)

        times = sorted([l.lap_time for l in valid])
        lap_count = len(times)
        if times:
            avg_lap = sum(times) / len(times)
            min_lap = times[0]
            max_lap = times[-1]
            q1 = times[int(len(times) * 0.25)] if len(times) >= 4 else min_lap
            median = times[int(len(times) * 0.5)] if len(times) >= 2 else times[0]
            q3 = times[int(len(times) * 0.75)] if len(times) >= 4 else max_lap
        else:
            avg_lap = min_lap = max_lap = q1 = median = q3 = None

        drivers = list(dict.fromkeys(l.driver_name for l in car_laps if l.driver_name))
        cm = car_model_map.get(str(car_num), car_laps[0].car_model if car_laps else "") or ""
        sc = car_color_map.get(str(car_num), car_laps[0].series_color if car_laps else "") or ""
        per_car.append({
            "car_number": car_num,
            "car_model": cm,
            "series_color": sc,
            "model_color": car_model_color_map.get(str(car_num), "") or "",
            "driver_name": ", ".join(drivers),
            "category": car_laps[0].category if car_laps else "",
            "lap_count": lap_count,
            "best_lap": best_lap.lap_time if best_lap else None,
            "best_s1": best_s1,
            "best_s2": best_s2,
            "best_s3": best_s3,
            "theoretical": theoretical,
            "top_speed": top_speed,
            "avg_lap": avg_lap,
            "min_lap": min_lap,
            "max_lap": max_lap,
            "q1": q1,
            "median": median,
            "q3": q3,
        })
    per_car.sort(key=lambda c: c["best_lap"] if c["best_lap"] else 99999)

    # All valid lap times (for line charts)
    lap_times = []
    for l in laps:
        if l.lap_time and l.lap_time > 0:
            median = car_median_clean.get(l.car_number)
            sc_lap = (l.lap_time > median * SC_THRESHOLD) if (median and not l.out_lap and not l.in_lap) else False
            lap_times.append({
                "car_number": l.car_number,
                "driver_name": l.driver_name,
                "lap_number": l.lap_number,
                "lap_time": l.lap_time,
                "sector_1": l.sector_1,
                "sector_2": l.sector_2,
                "sector_3": l.sector_3,
                "speed_trap_4": l.speed_trap_4,
                "is_best": l.is_best,
                "out_lap": l.out_lap,
                "in_lap": l.in_lap,
                "track_limit": l.track_limit,
                "sc_lap": sc_lap,
                "session_time": l.session_time,
            })

    # Overall best lap (exclude pit/SC/TL laps)
    all_valid = [
        l for l in laps if l.lap_time and l.lap_time > 0
        and not l.out_lap and not l.in_lap and not l.track_limit
    ]
    # Further filter SC laps for overall best
    clean_for_best = []
    for l in all_valid:
        median = car_median_clean.get(l.car_number)
        if not (median and l.lap_time > median * SC_THRESHOLD):
            clean_for_best.append(l)
    overall_best = min((l.lap_time for l in clean_for_best), default=None)

    # Pit stops
    pit_stops = []
    for car_num, car_laps in car_groups.items():
        clean = [l.lap_time for l in car_laps
                 if l.lap_time and l.lap_time > 0 and not l.out_lap and not l.in_lap]
        if not clean:
            clean = [l.lap_time for l in car_laps if l.lap_time and l.lap_time > 0]
        if not clean:
            continue
        clean_sorted = sorted(clean)
        median_clean = clean_sorted[len(clean_sorted) // 2]

        sorted_laps = sorted(car_laps, key=lambda x: x.lap_number)
        for i in range(len(sorted_laps) - 1):
            curr = sorted_laps[i]
            next_lap = sorted_laps[i + 1]
            if curr.in_lap and next_lap.out_lap:
                pit_time = _calculate_pit_stop_time(curr, next_lap)
                pit_stops.append({
                    "car_number": car_num,
                    "driver_name": curr.driver_name or "",
                    "in_lap": curr.lap_number,
                    "out_lap": next_lap.lap_number,
                    "pit_time": pit_time,
                })

    # Position progression (Race only)
    position_progression = None
    if session.session_type == "Race":
        lap_numbers = sorted(set(l.lap_number for l in all_valid))
        car_positions: dict[str, list] = {cn: [] for cn in car_groups}

        # Pre-build lookup: (car_number, lap_number) → driver_name
        lap_driver_map: dict[tuple[str, int], str] = {}
        for l in lap_times:
            lap_driver_map[(l["car_number"], l["lap_number"])] = l["driver_name"]

        for lap_num in lap_numbers:
            lap_entries = [l for l in all_valid if l.lap_number == lap_num]
            lap_entries.sort(key=lambda l: l.session_time if l.session_time else 999999)
            for pos, l in enumerate(lap_entries, 1):
                car_positions.setdefault(l.car_number, []).append({
                    "lap": lap_num,
                    "position": pos,
                })

        position_progression = {
            "lap_numbers": lap_numbers,
            "cars": {cn: car_positions[cn] for cn in car_positions if car_positions[cn]},
        }

    # Per-driver consistency (standard deviation of clean lap times)
    driver_laps_for_consistency: dict[str, list[float]] = {}
    for l in lap_times:
        if l["out_lap"] or l["in_lap"] or l["sc_lap"] or l["track_limit"]:
            continue
        if not l["lap_time"] or l["lap_time"] <= 0:
            continue
        name = l["driver_name"] or "Unknown"
        driver_laps_for_consistency.setdefault(name, []).append(l["lap_time"])

    driver_consistency = []
    for driver_name, times in driver_laps_for_consistency.items():
        if len(times) < 2:
            continue
        mean = sum(times) / len(times)
        variance = sum((t - mean) ** 2 for t in times) / len(times)
        std_dev = variance ** 0.5
        driver_consistency.append({
            "driver_name": driver_name,
            "std_dev": round(std_dev, 4),
            "lap_count": len(times),
            "avg_lap": round(mean, 4),
        })
    driver_consistency.sort(key=lambda d: d["std_dev"])

    # ── Car stints for strategy chart ───────────────────────────────
    standings_q = Standing.query.filter_by(session_id=session.id).all()
    standings_order: dict[str, dict] = {}
    for s in standings_q:
        standings_order[str(s.car_number)] = {
            "position": s.position,
            "is_classified": s.is_classified,
        }

    car_stints = []
    for car_num, car_laps in car_groups.items():
        sorted_laps = sorted(car_laps, key=lambda x: (x.lap_number or 0, x.session_time or 0))

        # Split into stints by out_lap
        stints: list[list[LapRecord]] = []
        current: list[LapRecord] = []
        for l in sorted_laps:
            if l.out_lap and current:
                stints.append(current)
                current = []
            current.append(l)
        if current:
            stints.append(current)

        stint_data = []
        for stint in stints:
            valid = [l for l in stint if l.lap_time and l.lap_time > 0]
            if not valid:
                continue
            driver = stint[0].driver_name or "Unknown"
            lap_count = len(stint)
            fastest_lap = min(l.lap_time for l in valid)

            # Determine stint time window from session_time
            times = [l.session_time for l in stint if l.session_time is not None]
            start_time = min(times) if times else None
            end_time = max(times) if times else None

            stint_data.append({
                "driver": driver,
                "lap_count": lap_count,
                "fastest_lap": fastest_lap,
                "start_time": start_time,
                "end_time": end_time,
            })

        if not stint_data:
            continue

        # Compute pit stop times between consecutive stints
        for i in range(1, len(stint_data)):
            prev_end = stint_data[i - 1]["end_time"]
            curr_start = stint_data[i]["start_time"]
            stint_data[i]["pit_time"] = (
                (curr_start - prev_end) if (prev_end and curr_start) else None
            )

        entry = standings_order.get(str(car_num))
        if entry and entry["position"] > 0 and entry["is_classified"]:
            display_pos = entry["position"]
        else:
            display_pos = None
        car_stints.append({
            "car_number": car_num,
            "car_model": car_model_map.get(str(car_num), car_laps[0].car_model if car_laps else "") or "",
            "series_color": car_color_map.get(str(car_num), car_laps[0].series_color if car_laps else "") or "",
            "model_color": car_model_color_map.get(str(car_num), car_laps[0].model_color if car_laps else "") or "",
            "position": display_pos,
            "stints": stint_data,
        })

    # Sort by classification position (None/0 = NC → at bottom)
    car_stints.sort(key=lambda c: c["position"] if (c["position"] is not None and c["position"] > 0) else 99999)

    result = {
        "session_name": session.name,
        "session_type": session.session_type,
        "per_car": per_car,
        "lap_times": lap_times,
        "overall_best_lap": overall_best,
        "pit_stops": pit_stops,
        "position_progression": position_progression,
        "driver_consistency": driver_consistency,
        "car_stints": car_stints,
    }
    _set_analytics_cache(session_id, result)
    return jsonify(result)
