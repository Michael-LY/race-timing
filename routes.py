import os
import time
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, current_app, session as flask_session)
from werkzeug.utils import secure_filename
from models import db, Event, Session, LapRecord, Standing, TimeKeeper, User
from parsers import get_parser, list_parsers
from datetime import datetime

bp = Blueprint("main", __name__)

ALLOWED_EXTENSIONS = {"csv", "txt"}

# Simple in-memory cache for analytics API
# Key: session_id, Value: (timestamp, data)
_analytics_cache: dict[int, tuple[float, dict]] = {}
_ANALYTICS_CACHE_TTL = 300  # 5 minutes
_ANALYTICS_CACHE_MAX = 50


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
            return redirect(url_for("main.index"))

    return render_template("register.html")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@bp.route("/")
def index():
    query = Event.query

    year = request.args.get("year", "").strip()
    championship = request.args.get("championship", "").strip()
    track = request.args.get("track", "").strip()

    if year:
        try:
            query = query.filter(Event.year == int(year))
        except ValueError:
            pass
    if championship:
        query = query.filter(Event.championship == championship)
    if track:
        query = query.filter(Event.track == track)

    events = query.order_by(Event.created_at.desc()).all()

    all_events = Event.query.all()
    years = sorted({e.year for e in all_events if e.year}, reverse=True)
    championships = sorted({e.championship for e in all_events if e.championship})
    tracks = sorted({e.track for e in all_events if e.track})

    return render_template("index.html", events=events,
                           years=years, championships=championships, tracks=tracks,
                           selected_year=year, selected_championship=championship,
                           selected_track=track)


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

        # Insert standings (from Classification)
        car_model_map: dict[str, str] = {}
        for s in data.get("standings", []):
            cm = s.get("car_model", "") or ""
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
                total_time=s.get("total_time"),
                gap=s.get("gap"),
                diff=s.get("diff"),
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
        # Mark best laps per car
        best_times: dict[str, float] = {}
        for l in laps_data:
            if l.get("lap_time") and l["lap_time"] > 0:
                key = l["car_number"]
                if key not in best_times or l["lap_time"] < best_times[key]:
                    best_times[key] = l["lap_time"]

        for l in laps_data:
            is_best = False
            if l.get("lap_time") and l["lap_time"] > 0:
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

    Returns (best_lap, best_s1_lap, best_s2_lap, best_s3_lap) or None for each.
    """
    best_lap = min(valid_laps, key=lambda l: l.lap_time) if valid_laps else None
    best_s1_lap = min((l for l in valid_laps if l.sector_1 and l.sector_1 > 0), key=lambda l: l.sector_1, default=None)
    best_s2_lap = min((l for l in valid_laps if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
    best_s3_lap = min((l for l in valid_laps if l.sector_3 and l.sector_3 > 0), key=lambda l: l.sector_3, default=None)
    return best_lap, best_s1_lap, best_s2_lap, best_s3_lap


def _compute_session_stats(laps: list[LapRecord]):
    """Compute overall and per-car bests across all sectors."""
    valid = [l for l in laps if l.lap_time and l.lap_time > 0]

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
        cv = [l for l in car_laps if l.lap_time and l.lap_time > 0]
        per_car_bests[car_num] = {
            "s1": min((l.sector_1 for l in cv if l.sector_1 and l.sector_1 > 0), default=None),
            "s2": min((l.sector_2 for l in cv if l.sector_2 and l.sector_2 > 0), default=None),
            "s3": min((l.sector_3 for l in cv if l.sector_3 and l.sector_3 > 0), default=None),
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
            valid_stint = [l for l in stint if l.lap_time and l.lap_time > 0]
            if not valid_stint:
                continue
            best_lap = min(valid_stint, key=lambda l: l.lap_time)
            best_s1  = min((l for l in valid_stint if l.sector_1 and l.sector_1 > 0), key=lambda l: l.sector_1, default=None)
            best_s2  = min((l for l in valid_stint if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
            best_s3  = min((l for l in valid_stint if l.sector_3 and l.sector_3 > 0), key=lambda l: l.sector_3, default=None)

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
        valid = [l for l in d_laps if l.lap_time and l.lap_time > 0]
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

    all_valid = [l for l in laps if l.lap_time and l.lap_time > 0]
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
        valid = [l for l in car_laps if l.lap_time and l.lap_time > 0]
        best_lap = min(valid, key=lambda x: x.lap_time) if valid else None
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
                           overall_best_theoretical=overall_best_theoretical)


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
# API — lap data for charts
# ---------------------------------------------------------------------------
@bp.route("/api/sessions/<int:session_id>/laps")
def api_session_laps(session_id):
    session = Session.query.get_or_404(session_id)
    laps = []
    for l in session.laps:
        laps.append({
            "car_number": l.car_number,
            "driver_name": l.driver_name,
            "lap_number": l.lap_number,
            "lap_time": l.lap_time,
            "sector_1": l.sector_1,
            "sector_2": l.sector_2,
            "sector_3": l.sector_3,
            "is_best": l.is_best,
            "out_lap": l.out_lap,
            "in_lap": l.in_lap,
            "session_time": l.session_time,
        })
    return jsonify({"session_name": session.name, "session_type": session.session_type, "laps": laps})


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
            if l.lap_time and l.lap_time > 0 and not l.out_lap and not l.in_lap
        ])
        if clean:
            car_median_clean[car_num] = clean[len(clean) // 2]

    # Build car_model map from standings
    car_model_map: dict[str, str] = {}
    for s in session.standings:
        if s.car_model:
            car_model_map[str(s.car_number)] = s.car_model

    # Per-car stats
    per_car = []
    for car_num, car_laps in car_groups.items():
        median = car_median_clean.get(car_num)
        valid = [l for l in car_laps if l.lap_time and l.lap_time > 0
                 and not l.out_lap and not l.in_lap
                 and not (median and l.lap_time > median * SC_THRESHOLD)]
        if not valid:
            valid = [l for l in car_laps if l.lap_time and l.lap_time > 0]

        best_lap = min(valid, key=lambda l: l.lap_time) if valid else None
        best_s1 = min((l.sector_1 for l in valid if l.sector_1 and l.sector_1 > 0), default=None)
        best_s2 = min((l.sector_2 for l in valid if l.sector_2 and l.sector_2 > 0), default=None)
        best_s3 = min((l.sector_3 for l in valid if l.sector_3 and l.sector_3 > 0), default=None)
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
        per_car.append({
            "car_number": car_num,
            "car_model": cm,
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
                "sc_lap": sc_lap,
                "session_time": l.session_time,
            })

    # Overall best lap (exclude pit/SC laps)
    all_valid = [
        l for l in laps if l.lap_time and l.lap_time > 0
        and not l.out_lap and not l.in_lap
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
        if l["out_lap"] or l["in_lap"] or l["sc_lap"]:
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
