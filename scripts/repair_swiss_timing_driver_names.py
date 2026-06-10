import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from models import db, Session, LapRecord
from parsers.swiss_timing import SwissTimingParser


def _extract_upload_prefix(path: Path) -> str | None:
    name = path.name
    if not name:
        return None
    prefix = name.split("_", 1)[0]
    if len(prefix) == 14 and prefix.isdigit():
        return prefix
    return None


def _find_matching_upload_files(prefix: str) -> dict[str, Path | None]:
    upload_dir = ROOT / "uploads"
    files = [p for p in upload_dir.iterdir() if p.is_file() and p.name.startswith(prefix)]

    def pick(keyword: str) -> Path | None:
        for path in files:
            lower = path.name.lower()
            if keyword in lower:
                return path
        return None

    return {
        "sector": pick("sec") or pick("sector"),
        "classification": pick("cls") or pick("classification"),
        "pitstops": pick("pit"),
        "tlw": pick("tlw"),
        "messages": pick("msg"),
    }


def repair_swiss_timing_sessions() -> int:
    app = create_app()
    with app.app_context():
        parser = SwissTimingParser()
        sessions = Session.query.all()
        upload_dir = ROOT / "uploads"
        prefixes: dict[str, list[Path]] = {}

        if upload_dir.exists():
            for path in upload_dir.iterdir():
                if not path.is_file():
                    continue
                prefix = _extract_upload_prefix(path)
                if prefix:
                    prefixes.setdefault(prefix, []).append(path)

        updated_sessions = 0
        for session in sessions:
            if not session.event or not session.event.time_keeper:
                continue
            if session.event.time_keeper.parser_module != "swiss_timing":
                continue

            session_dt = session.start_time or session.created_at
            if not session_dt:
                continue

            session_dt = session_dt.replace(tzinfo=None)
            best_prefix = None
            best_diff = None
            for prefix in prefixes:
                try:
                    parsed_dt = datetime.strptime(prefix, "%Y%m%d%H%M%S")
                except ValueError:
                    continue
                diff = abs((parsed_dt - session_dt).total_seconds())
                if diff <= 300 and (best_diff is None or diff < best_diff):
                    best_diff = diff
                    best_prefix = prefix

            if not best_prefix:
                continue

            files = _find_matching_upload_files(best_prefix)
            sector_path = files.get("sector")
            classification_path = files.get("classification")
            pitstops_path = files.get("pitstops")
            if not sector_path:
                continue

            parsed = parser.parse(
                sector_path=str(sector_path),
                classification_path=str(classification_path) if classification_path else None,
                pitstops_path=str(pitstops_path) if pitstops_path else None,
            )

            parsed_laps = {}
            for lap in parsed.get("laps", []):
                if lap.get("car_number") is None or lap.get("lap_number") is None:
                    continue
                parsed_laps[(str(lap["car_number"]), int(lap["lap_number"]))] = lap

            updated_laps = 0
            for lap_record in session.laps:
                parsed_lap = parsed_laps.get((str(lap_record.car_number), int(lap_record.lap_number)))
                if not parsed_lap:
                    continue
                lap_record.driver_name = parsed_lap.get("driver_name", lap_record.driver_name)
                lap_record.in_lap = bool(parsed_lap.get("in_lap", False))
                lap_record.out_lap = bool(parsed_lap.get("out_lap", False))
                updated_laps += 1

            db.session.commit()
            updated_sessions += 1
            print(f"Updated session {session.id} ({session.name}) with {updated_laps} laps")

        return updated_sessions


if __name__ == "__main__":
    count = repair_swiss_timing_sessions()
    print(f"Repaired {count} Swiss Timing session(s)")
