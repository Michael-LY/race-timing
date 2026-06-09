import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from werkzeug.utils import secure_filename
from models import db, Event, Session, LapRecord, Standing, TimeKeeper
from parsers import get_parser, list_parsers
from datetime import datetime

bp = Blueprint("main", __name__)

ALLOWED_EXTENSIONS = {"csv", "txt"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@bp.route("/")
def index():
    events = Event.query.order_by(Event.created_at.desc()).all()
    return render_template("index.html", events=events)


# ---------------------------------------------------------------------------
# Create event
# ---------------------------------------------------------------------------
@bp.route("/events/new", methods=["GET", "POST"])
def event_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        track = request.form.get("track", "").strip()
        date_str = request.form.get("event_date", "").strip()

        if not name:
            flash("Event name is required", "danger")
            return redirect(url_for("main.event_create"))

        event = Event(name=name, track=track)
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
def event_delete(event_id):
    event = Event.query.get_or_404(event_id)
    name = event.name
    db.session.delete(event)
    db.session.commit()
    flash(f'Event "{name}" deleted', "success")
    return redirect(url_for("main.index"))


# ---------------------------------------------------------------------------
# Upload CSV(s)
# ---------------------------------------------------------------------------
@bp.route("/events/<int:event_id>/upload", methods=["GET", "POST"])
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

        # Create session
        session = Session(
            event_id=event.id,
            name=data.get("session_name", "Untitled"),
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

    return overall, per_car_bests, car_groups


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------
@bp.route("/sessions/<int:session_id>")
def session_detail(session_id):
    session = Session.query.get_or_404(session_id)
    standings = session.standings
    laps = session.laps

    overall, per_car_bests, car_groups = _compute_session_stats(laps)

    # Per-car summary
    car_summaries = []
    for car_num, car_laps in car_groups.items():
        valid = [l for l in car_laps if l.lap_time and l.lap_time > 0]
        best_lap = min(valid, key=lambda x: x.lap_time) if valid else None
        drivers = list(dict.fromkeys(l.driver_name for l in car_laps if l.driver_name))
        pcb = per_car_bests.get(car_num, {})
        car_summaries.append({
            "car_number": car_num,
            "driver": ", ".join(drivers),
            "category": car_laps[0].category if car_laps else "",
            "total_laps": len(car_laps),
            "best_lap": best_lap.lap_time if best_lap else None,
            "sector_1": best_lap.sector_1 if best_lap else None,
            "sector_2": best_lap.sector_2 if best_lap else None,
            "sector_3": best_lap.sector_3 if best_lap else None,
            "best_s1": pcb.get("s1"),
            "best_s2": pcb.get("s2"),
            "best_s3": pcb.get("s3"),
            "speed": best_lap.speed if best_lap else None,
        })
    car_summaries.sort(key=lambda x: x["best_lap"] if x["best_lap"] else 99999)

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
                           driver_overall_s3=driver_overall_s3)


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
def session_delete(session_id):
    session = Session.query.get_or_404(session_id)
    event_id = session.event_id
    name = session.name
    db.session.delete(session)
    db.session.commit()
    flash(f'Session "{name}" deleted', "success")
    return redirect(url_for("main.event_detail", event_id=event_id))


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
        })
    return jsonify({"session_name": session.name, "session_type": session.session_type, "laps": laps})
