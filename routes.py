import os
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, current_app, session as flask_session)
from werkzeug.utils import secure_filename
from models import db, Event, Session, LapRecord, Standing, TimeKeeper, User
from parsers import get_parser, list_parsers
from datetime import datetime

bp = Blueprint("main", __name__)

ALLOWED_EXTENSIONS = {"csv", "txt"}


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

    # Distinct filter options from all events
    years = sorted(set(e.year for e in Event.query.all() if e.year), reverse=True)
    championships = sorted(set(e.championship for e in Event.query.all() if e.championship))
    tracks = sorted(set(e.track for e in Event.query.all() if e.track))

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

        if not cls_file and not sec_file:
            flash("Please upload at least one CSV file", "danger")
            return redirect(url_for("main.upload", event_id=event_id))

        # Validate that uploaded files are CSVs
        for f in (cls_file, sec_file):
            if f and f.filename and not allowed_file(f.filename):
                flash(f"'{f.filename}' is not a CSV file", "danger")
                return redirect(url_for("main.upload", event_id=event_id))

        # Save files
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        cls_path = None
        sec_path = None

        if cls_file and cls_file.filename:
            cls_name = secure_filename(cls_file.filename)
            cls_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{ts}_cls_{cls_name}")
            cls_file.save(cls_path)

        if sec_file and sec_file.filename:
            sec_name = secure_filename(sec_file.filename)
            sec_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{ts}_sec_{sec_name}")
            sec_file.save(sec_path)

        # Parse
        try:
            data = parser.parse(classification_path=cls_path, sector_path=sec_path)
        except Exception as e:
            flash(f"Parse error: {e}", "danger")
            return redirect(url_for("main.upload", event_id=event_id))

        # Link time keeper
        tk = TimeKeeper.query.filter_by(parser_module=parser_key).first()
        if tk:
            event.time_keeper_id = tk.id

        # Create session — use custom name if provided, otherwise parser default
        custom_name = request.form.get("session_name", "").strip()
        session = Session(
            event_id=event.id,
            name=custom_name if custom_name else data.get("session_name", "Untitled"),
            session_type=data.get("session_type", "Practice"),
            start_time=datetime.utcnow(),
        )
        db.session.add(session)
        db.session.flush()

        # Insert standings (from Classification)
        for s in data.get("standings", []):
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

            lap = LapRecord(
                session_id=session.id,
                car_number=l.get("car_number", ""),
                driver_name=l.get("driver_name", ""),
                category=l.get("category", ""),
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

    return render_template("upload.html", event=event, parsers=parsers, selected_parser=selected_parser)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _compute_session_stats(laps: list[LapRecord]):
    """Compute overall and per-car bests across all sectors."""
    valid = [l for l in laps if l.lap_time and l.lap_time > 0]

    overall_best_lap = min(valid, key=lambda l: l.lap_time) if valid else None
    overall_best_s1  = min((l for l in valid if l.sector_1 and l.sector_1 > 0), key=lambda l: l.sector_1, default=None)
    overall_best_s2  = min((l for l in valid if l.sector_2 and l.sector_2 > 0), key=lambda l: l.sector_2, default=None)
    overall_best_s3  = min((l for l in valid if l.sector_3 and l.sector_3 > 0), key=lambda l: l.sector_3, default=None)

    overall = {
        "lap_time": overall_best_lap.lap_time if overall_best_lap else None,
        "lap_car": overall_best_lap.car_number if overall_best_lap else "",
        "s1": overall_best_s1.sector_1 if overall_best_s1 else None,
        "s1_car": overall_best_s1.car_number if overall_best_s1 else "",
        "s2": overall_best_s2.sector_2 if overall_best_s2 else None,
        "s2_car": overall_best_s2.car_number if overall_best_s2 else "",
        "s3": overall_best_s3.sector_3 if overall_best_s3 else None,
        "s3_car": overall_best_s3.car_number if overall_best_s3 else "",
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
# Session detail
# ---------------------------------------------------------------------------
@bp.route("/sessions/<int:session_id>")
def session_detail(session_id):
    session = Session.query.get_or_404(session_id)
    standings = session.standings
    laps = session.laps

    overall, per_car_bests, car_groups, stint_bests = _compute_session_stats(laps)

    # Per-car summary
    car_summaries = []
    for car_num, car_laps in car_groups.items():
        valid = [l for l in car_laps if l.lap_time and l.lap_time > 0]
        best_lap = min(valid, key=lambda x: x.lap_time) if valid else None
        drivers = list(dict.fromkeys(l.driver_name for l in car_laps if l.driver_name))
        pcb = per_car_bests.get(car_num, {})
        s1 = pcb.get("s1")
        s2 = pcb.get("s2")
        s3 = pcb.get("s3")
        theoretical = (s1 + s2 + s3) if (s1 and s2 and s3) else None
        car_summaries.append({
            "car_number": car_num,
            "driver": ", ".join(drivers),
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

    # Overall best theoretical
    overall_best_theoretical = min((c["theoretical"] for c in car_summaries if c["theoretical"]), default=None)

    # Driver analysis data (same as /drivers route)
    driver_groups: dict[str, list[LapRecord]] = {}
    for l in laps:
        name = l.driver_name.strip() if l.driver_name else "Unknown"
        driver_groups.setdefault(name, []).append(l)

    drivers = []
    for name, d_laps in driver_groups.items():
        valid = [l for l in d_laps if l.lap_time and l.lap_time > 0]
        best_lap = min(valid, key=lambda l: l.lap_time) if valid else None
        best_s1 = min((l.sector_1 for l in valid if l.sector_1 and l.sector_1 > 0), default=None)
        best_s2 = min((l.sector_2 for l in valid if l.sector_2 and l.sector_2 > 0), default=None)
        best_s3 = min((l.sector_3 for l in valid if l.sector_3 and l.sector_3 > 0), default=None)
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
    driver_overall_s1 = min((l.sector_1 for l in all_valid if l.sector_1 and l.sector_1 > 0), default=None)
    driver_overall_s2 = min((l.sector_2 for l in all_valid if l.sector_2 and l.sector_2 > 0), default=None)
    driver_overall_s3 = min((l.sector_3 for l in all_valid if l.sector_3 and l.sector_3 > 0), default=None)

    return render_template("session_detail.html",
                           session=session,
                           standings=standings,
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

    # Group by driver
    driver_groups: dict[str, list[LapRecord]] = {}
    for l in laps:
        name = l.driver_name.strip() if l.driver_name else "Unknown"
        driver_groups.setdefault(name, []).append(l)

    drivers = []
    for name, driver_laps in driver_groups.items():
        valid = [l for l in driver_laps if l.lap_time and l.lap_time > 0]
        best_lap = min(valid, key=lambda l: l.lap_time) if valid else None

        best_s1 = min((l.sector_1 for l in valid if l.sector_1 and l.sector_1 > 0), default=None)
        best_s2 = min((l.sector_2 for l in valid if l.sector_2 and l.sector_2 > 0), default=None)
        best_s3 = min((l.sector_3 for l in valid if l.sector_3 and l.sector_3 > 0), default=None)

        theoretical = None
        if best_s1 and best_s2 and best_s3:
            theoretical = best_s1 + best_s2 + best_s3

        car_number = driver_laps[0].car_number if driver_laps else ""

        drivers.append({
            "driver_name": name,
            "car_number": car_number,
            "total_laps": len(valid),
            "best_lap": best_lap.lap_time if best_lap else None,
            "best_s1": best_s1,
            "best_s2": best_s2,
            "best_s3": best_s3,
            "theoretical": theoretical,
        })

    # Sort by best lap
    drivers.sort(key=lambda d: d["best_lap"] if d["best_lap"] else 99999)

    # Overall sector bests across all drivers
    all_valid = [l for l in laps if l.lap_time and l.lap_time > 0]
    overall_best_s1 = min((l.sector_1 for l in all_valid if l.sector_1 and l.sector_1 > 0), default=None)
    overall_best_s2 = min((l.sector_2 for l in all_valid if l.sector_2 and l.sector_2 > 0), default=None)
    overall_best_s3 = min((l.sector_3 for l in all_valid if l.sector_3 and l.sector_3 > 0), default=None)

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
    db.session.delete(session)
    db.session.commit()
    flash(f'Session "{name}" deleted', "success")
    return redirect(url_for("main.event_detail", event_id=event_id))


# ---------------------------------------------------------------------------
# Edit session
# ---------------------------------------------------------------------------
SESSION_TYPES = ["Practice", "Qualifying", "Race", "Paid Test"]


@bp.route("/sessions/<int:session_id>/edit", methods=["GET", "POST"])
@admin_required
def session_edit(session_id):
    session = Session.query.get_or_404(session_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        session_type = request.form.get("session_type", "").strip()

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
        per_car.append({
            "car_number": car_num,
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
                pit_time = (next_lap.lap_time - median_clean) if next_lap.lap_time else None
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
        # For each lap, determine each car's position based on cumulative time
        # Group laps by lap_number, then rank by cumulative time
        lap_numbers = sorted(set(l.lap_number for l in all_valid))
        car_positions: dict[str, list] = {cn: [] for cn in car_groups}

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

    return jsonify({
        "session_name": session.name,
        "session_type": session.session_type,
        "per_car": per_car,
        "lap_times": lap_times,
        "overall_best_lap": overall_best,
        "pit_stops": pit_stops,
        "position_progression": position_progression,
    })
