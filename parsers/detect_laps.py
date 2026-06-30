"""Standalone lap detection functions for out_lap, in_lap, and track_limit.

Extracted from SwissTimingParser so they can be reused for retroactive
DB updates without re-uploading CSV files.
"""

import csv


def parse_tlw_file(filepath: str) -> list[dict]:
    """Parse TLWlistMessage CSV file.

    Columns: Bib;Date & Time;Race time;TL at Turn;Message
    """
    warnings = []

    # Detect encoding (try UTF-8-sig first, fall back to Latin-1)
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(filepath, newline="", encoding=enc) as f:
                rows = list(csv.reader(f, delimiter=";"))
            break
        except UnicodeDecodeError:
            continue
    else:
        return warnings

    for row in rows[1:]:
        if not row or len(row) < 4:
            continue
        bib = row[0].strip()
        if not bib or not bib.isdigit():
            continue
        race_time = _to_seconds(row[2].strip())
        turn = row[3].strip() if len(row) > 3 else ""
        warnings.append({
            "car_number": bib,
            "race_time": race_time,
            "turn": turn,
            "message": row[4].strip() if len(row) > 4 else "",
        })
    return warnings


def _to_seconds(time_str: str) -> float | None:
    """Convert Swiss Timing time string to seconds."""
    if not time_str:
        return None
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        else:
            return float(time_str)
    except (ValueError, TypeError):
        return None


def detect_out_laps(laps: list[dict]) -> None:
    """Detect out laps: first lap of each stint.

    Stint boundaries are detected by:
    - Duplicate lap numbers (first duplicate is out lap)
    - Gaps in lap numbers (e.g., 1,2,3 then 5,6 — gap indicates new stint)
    - The very first lap of each car is also an out lap
    """
    car_groups: dict[str, list[dict]] = {}
    for l in laps:
        car_groups.setdefault(l["car_number"], []).append(l)

    for car_num, car_laps in car_groups.items():
        car_laps.sort(key=lambda x: x["lap_number"])
        if not car_laps:
            continue

        car_laps[0]["out_lap"] = True

        for i in range(1, len(car_laps)):
            prev = car_laps[i - 1]
            curr = car_laps[i]
            if curr["lap_number"] == prev["lap_number"]:
                prev["out_lap"] = True
            elif curr["lap_number"] > prev["lap_number"] + 1:
                curr["out_lap"] = True


def detect_in_laps(laps: list[dict]) -> None:
    """Heuristic in-lap detection when no PitStopsCsv is available.

    A lap is flagged as in_lap if its lap_time exceeds 1.2x the median
    of clean laps (excluding the first lap which is a standing start).
    """
    car_groups: dict[str, list[dict]] = {}
    for l in laps:
        car_groups.setdefault(l["car_number"], []).append(l)

    for car_num, car_laps in car_groups.items():
        car_laps.sort(key=lambda x: x["lap_number"])
        clean = sorted([
            l["lap_time"] for l in car_laps
            if l["lap_number"] > 1 and l.get("lap_time") and l["lap_time"] > 0
        ])
        if len(clean) < 2:
            continue
        median = clean[(len(clean) - 1) // 2]
        for l in car_laps:
            if l["lap_number"] > 1 and l.get("lap_time") and l["lap_time"] > median * 1.2:
                l["in_lap"] = True


def apply_tlw(laps: list[dict], warnings: list[dict]) -> None:
    """Match TLW warnings to laps and set track_limit flag.

    Each warning's race_time (cumulative seconds) is matched to the lap
    whose session_time range contains it.
    """
    if not warnings:
        return

    car_warnings: dict[str, list[dict]] = {}
    for w in warnings:
        car_warnings.setdefault(w["car_number"], []).append(w)

    car_laps: dict[str, list[dict]] = {}
    for lap in laps:
        car_laps.setdefault(lap["car_number"], []).append(lap)

    for car_num, car_ws in car_warnings.items():
        c_laps = sorted(car_laps.get(car_num, []), key=lambda x: x["lap_number"])
        if not c_laps:
            continue

        car_ws_sorted = sorted(car_ws, key=lambda w: w["race_time"])

        for w in car_ws_sorted:
            rt = w["race_time"]
            if rt is None:
                continue

            matched = False
            for i, lap in enumerate(c_laps):
                st = lap.get("session_time")
                if st is None:
                    continue

                if i == 0:
                    if rt <= st:
                        lap["track_limit"] = True
                        matched = True
                        break
                else:
                    prev_st = c_laps[i - 1].get("session_time")
                    if prev_st is not None and prev_st < rt <= st:
                        lap["track_limit"] = True
                        matched = True
                        break
                    elif prev_st is None and rt <= st:
                        lap["track_limit"] = True
                        matched = True
                        break

            if not matched and c_laps:
                last = c_laps[-1]
                last_st = last.get("session_time")
                if last_st is not None and rt > last_st:
                    last["track_limit"] = True
