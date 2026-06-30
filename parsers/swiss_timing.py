"""Swiss Timing parser — handles SectorListCSV + optional ResultListCSV, PitStopsCsv,
TLWlistMessage, and MessageListCSV.

Swiss Timing CSV files use semicolon (;) delimiters and typically use Latin-1
encoding (Sector/Result/PitStops) or UTF-8 (TLW/Message).
"""

import csv
import os
import re

from parsers.detect_laps import detect_out_laps, detect_in_laps, apply_tlw
from typing import Any

from .base import BaseParser


class SwissTimingParser(BaseParser):
    """Parses Swiss Timing CSV exports.

    Five file types (only SectorListCSV is required):

      SectorListCSV (required):
          Bib;Class;Driver1;...;Car;Lap;Time;Sector1Time;SpeedTrap1;
          Sector2Time;SpeedTrap2;Sector3Time;SpeedTrap3;TopSpeed
          Note: headers repeat periodically; parser automatically filters them.

      ResultListCSV (optional):
          Rank;Bib;ClassName;Driver1;...;CarName;TeamName;...;
          TotalTime;LapCount;GapTime;GapLap;BestLapAverageSpeed;
          BestLapTime;BestLapLapNumber;State

      PitStopsCsv (optional):
          Nr;Driver in;Day time in;Time in;Driver out;Day time out;
          Time out;Nett Time;Reason;Lap In

      TLWlistMessage (optional):
          Bib;Date & Time;Race time;TL at Turn;Message

      MessageListCSV (optional):
          TIME;RACE TIME;MESSAGE
    """

    name = "Swiss Timing"
    description = (
        "Swiss Timing — SectorListCSV (required) + optional ResultListCSV, "
        "PitStopsCsv, TLWlistMessage, MessageListCSV"
    )

    SESSION_TYPE_KEYWORDS = {
        "Practice": ["practice", "free practice", "fp", "p "],
        "Qualifying": ["qualifying", "qual", "q ", "qualification"],
        "Race": ["race", "r ", "_r_"],
        "Paid-Test": ["paid test", "paidtest", "paid_test"],
        "Bronze-Session": ["bronze session", "bronzesession", "bronze_session"],
        "Pre-Qualifying": [
            "pre-qualifying", "prequalifying", "pre_qualifying",
            "pre-qual", "prequal",
        ],
        "Warm-up": ["warm-up", "warmup", "warm_up"],
    }

    # ── time parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _to_seconds(val: str) -> float | None:
        """Parse Swiss Timing time formats: M:SS.fff or H:MM:SS.fff or SS.f"""
        if not val or not val.strip():
            return None
        val = val.strip()
        # H:MM:SS.fff (e.g. "3:01:03.675")
        m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})\.(\d+)", val)
        if m:
            return (
                int(m.group(1)) * 3600
                + int(m.group(2)) * 60
                + int(m.group(3))
                + int(m.group(4)) / 1000
            )
        # M:SS.fff (e.g. "1:47.306")
        m = re.fullmatch(r"(\d+):(\d{2})\.(\d+)", val)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 1000
        # SS.fff
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def _parse_speed(val: str) -> float | None:
        """Parse speed value (integer km/h)."""
        if not val or not val.strip():
            return None
        try:
            return float(val.strip())
        except ValueError:
            return None

    @staticmethod
    def _detect_encoding(filepath: str) -> str:
        """Detect file encoding. Swiss Timing uses Latin-1 for data files,
        UTF-8-sig for message files. Try UTF-8-sig first, fall back to Latin-1."""
        encodings = ["utf-8-sig", "latin-1"]
        for enc in encodings:
            try:
                with open(filepath, newline="", encoding=enc) as f:
                    f.read()
                return enc
            except UnicodeDecodeError:
                continue
        return "latin-1"

    # ── session-type detection ────────────────────────────────────────────

    def _detect_session_type(self, filepath: str) -> str:
        name = os.path.basename(filepath).lower()
        for stype, keywords in self.SESSION_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in name:
                    return stype
        return "Practice"

    # ── detect ────────────────────────────────────────────────────────────

    def detect(self, filepath: str) -> bool:
        """Return True if this looks like a Swiss Timing CSV."""
        try:
            enc = self._detect_encoding(filepath)
            with open(filepath, newline="", encoding=enc) as f:
                content = f.read(2048)
            # Swiss Timing uses semicolon delimiters and distinctive headers
            if ";" not in content:
                return False
            lower = content.lower()
            # SectorListCSV markers
            if "bib" in lower and "sector1time" in lower:
                return True
            # ResultListCSV markers
            if "rank" in lower and "bib" in lower and "bestlaptime" in lower:
                return True
            # PitStopsCsv markers
            if "driver in" in lower and "nett time" in lower:
                return True
            # TLWlistMessage markers
            if "tl at turn" in lower:
                return True
            return False
        except Exception:
            return False

    # ── parse ─────────────────────────────────────────────────────────────

    def parse(
        self,
        sector_path: str = None,
        classification_path: str = None,
        pitstops_path: str = None,
        tlw_path: str = None,
        messages_path: str = None,
    ) -> dict[str, Any]:
        """Parse Swiss Timing CSV files.

        Args:
            sector_path: Path to SectorListCSV (required)
            classification_path: Path to ResultListCSV (optional)
            pitstops_path: Path to PitStopsCsv (optional)
            tlw_path: Path to TLWlistMessage (optional)
            messages_path: Path to MessageListCSV (optional)

        Returns dict with keys: session_name, session_type, laps, standings
        """
        result: dict[str, Any] = {
            "session_name": "",
            "session_type": "Practice",
            "laps": [],
            "standings": [],
        }

        # 1. Parse SectorListCSV (required — core lap data)
        if sector_path:
            laps, sec_name, sec_type = self._parse_sector(sector_path)
            result["laps"] = laps
            result["session_name"] = sec_name or result["session_name"]
            result["session_type"] = sec_type or result["session_type"]
        else:
            raise ValueError("SectorListCSV is required for Swiss Timing parser")

        # 2. Parse ResultListCSV (optional — classification)
        if classification_path:
            standings, cls_name, cls_type = self._parse_result_list(
                classification_path
            )
            result["standings"] = standings
            if cls_name:
                result["session_name"] = cls_name
            if cls_type:
                result["session_type"] = cls_type

        # 3. Parse PitStopsCsv (optional — enrich lap pit markers)
        if pitstops_path:
            pit_laps = self._parse_pitstops(pitstops_path)
            self._apply_pitstops(result["laps"], pit_laps)
        else:
            # No PitStopsCsv: detect in laps heuristically from sector data
            self._detect_in_laps(result["laps"])

        # 4. Parse TLWlistMessage (optional — track limit warnings)
        if tlw_path:
            tlw_warnings = self._parse_tlw(tlw_path)
            result["_tlw_warnings"] = tlw_warnings
            self._apply_tlw(result["laps"], tlw_warnings)

        # 5. Parse MessageListCSV (optional — race control messages)
        if messages_path:
            msgs = self._parse_messages(messages_path)
            result["_messages"] = msgs

        # Build standings from sector data if no ResultListCSV
        if not result["standings"]:
            result["standings"] = self._build_standings_from_laps(result["laps"])

        # Propagate car_model from standings to laps
        if result["standings"]:
            model_map: dict[str, str] = {}
            for s in result["standings"]:
                cn = str(s.get("car_number", ""))
                cm = s.get("car_model", "")
                if cn and cm:
                    model_map[cn] = cm
            for lap in result["laps"]:
                cn = str(lap.get("car_number", ""))
                if cn in model_map:
                    lap["car_model"] = model_map[cn]

        if not result["session_name"]:
            result["session_name"] = result["session_type"]

        return result

    # ── SectorListCSV ─────────────────────────────────────────────────────

    def _parse_sector(self, filepath: str) -> tuple[list[dict], str, str]:
        """Parse SectorListCSV.

        Columns: Bib;Class;Driver1;Driver2;Driver3;Driver4;Car;
                 Lap;Time;Sector1Time;SpeedTrap1;Sector2Time;
                 SpeedTrap2;Sector3Time;SpeedTrap3;TopSpeed

        Header row repeats every ~12 laps — must filter out.
        """
        laps = []
        session_name = ""
        session_type = self._detect_session_type(filepath)
        enc = self._detect_encoding(filepath)

        # Try to extract session name from filename
        base = os.path.splitext(os.path.basename(filepath))[0]
        parts = base.split("_")
        if len(parts) >= 4:
            # Format: GTWCEU_GT3_R_SectorListCSV_1.0
            # Parts[2] = session letter (R/Q/P)
            session_name = f"{parts[0]} {parts[1]} {parts[2]}"

        with open(filepath, newline="", encoding=enc) as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)

        if not rows:
            return [], session_name, session_type

        # Find first header row for column mapping
        header = None
        header_idx = 0
        for i, row in enumerate(rows):
            if not row:
                continue
            first = row[0].strip().lower()
            if first == "bib" and len(row) >= 10:
                header = [c.strip() for c in row]
                header_idx = i
                break

        if header is None:
            return [], session_name, session_type

        # Build column index map
        col = {}
        for idx, name in enumerate(header):
            col[name.lower()] = idx

        def get_col(row, *aliases):
            for alias in aliases:
                if alias in col and col[alias] < len(row):
                    return row[col[alias]].strip()
            return ""

        # Parse all rows, filtering out repeated headers
        for row in rows[header_idx:]:
            if not row or len(row) < 8:
                continue
            first = row[0].strip().lower()
            if first == "bib":
                # Repeated header — skip
                continue
            if not first.isdigit():
                continue

            bib = first
            lap_str = get_col(row, "lap")
            if not lap_str:
                continue
            try:
                lap_number = int(lap_str)
            except ValueError:
                continue

            # Detect out/in laps from lap time patterns
            # A >50% increase vs adjacent laps typically indicates pit stop
            lap_time = self._to_seconds(get_col(row, "time"))
            top_speed = None
            ts_val = get_col(row, "topspeed")
            if ts_val:
                top_speed = self._parse_speed(ts_val)

            laps.append({
                "car_number": bib,
                "driver_name": "",  # resolved after all laps collected
                "category": get_col(row, "class"),
                "lap_number": lap_number,
                "lap_time": lap_time,
                "sector_1": self._to_seconds(get_col(row, "sector1time")),
                "sector_2": self._to_seconds(get_col(row, "sector2time")),
                "sector_3": self._to_seconds(get_col(row, "sector3time")),
                "speed_trap_1": self._parse_speed(get_col(row, "speedtrap1")),
                "speed_trap_2": self._parse_speed(get_col(row, "speedtrap2")),
                "speed_trap_3": self._parse_speed(get_col(row, "speedtrap3")),
                "speed_trap_4": top_speed,  # TopSpeed → SpeedTrap4
                "speed": top_speed,
                "out_lap": False,
                "in_lap": False,
                "time_of_day": "",
                "session_time": None,
                "position": None,
                "driver1": get_col(row, "driver1"),
                "driver2": get_col(row, "driver2"),
                "driver3": get_col(row, "driver3"),
                "driver4": get_col(row, "driver4"),
            })

        # Sort by car number then lap number
        laps.sort(key=lambda x: (str(x["car_number"]).zfill(4), x["lap_number"]))

        # Detect out laps from duplicate lap numbers (Swiss Timing data error)
        self._detect_out_laps(laps)

        # Calculate session_time as cumulative lap time per car
        self._compute_session_times(laps)

        # Assign driver names and detect pit in/out laps
        self._assign_drivers_and_pits(laps)

        return laps, session_name, session_type

    # ── ResultListCSV ─────────────────────────────────────────────────────

    def _parse_result_list(
        self, filepath: str
    ) -> tuple[list[dict], str, str]:
        """Parse ResultListCSV.

        Columns: Rank;Bib;ClassName;Driver1;...;CarName;TeamName;
                 LicenceHolderName;TotalTime;LapCount;GapTime;GapLap;
                 BestLapAverageSpeed;BestLapTime;BestLapLapNumber;State
        """
        standings = []
        session_name = ""
        session_type = self._detect_session_type(filepath)
        enc = self._detect_encoding(filepath)

        base = os.path.splitext(os.path.basename(filepath))[0]
        parts = base.split("_")
        if len(parts) >= 4:
            session_name = f"{parts[0]} {parts[1]} {parts[2]}"

        with open(filepath, newline="", encoding=enc) as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)

        if not rows:
            return [], session_name, session_type

        # Find header
        header_idx = 0
        for i, row in enumerate(rows):
            if not row:
                continue
            first = row[0].strip().lower()
            if first == "rank" and len(row) >= 10:
                header_idx = i
                break

        h = [c.strip().lower() for c in rows[header_idx]]
        col = {}
        for idx, name in enumerate(h):
            col[name] = idx

        def get_col(row, *aliases):
            for alias in aliases:
                if alias in col and col[alias] < len(row):
                    return row[col[alias]].strip()
            return ""

        for row in rows[header_idx + 1 :]:
            if not row or all(c.strip() == "" for c in row):
                continue

            rank_str = get_col(row, "rank")
            bib = get_col(row, "bib")
            if not bib:
                continue

            is_classified = True
            position = 0
            if rank_str:
                try:
                    position = int(rank_str)
                except ValueError:
                    position = 0
                    is_classified = False
                else:
                    is_classified = position > 0
            else:
                is_classified = False

            car_model = get_col(row, "carname")
            if not car_model:
                car_model = get_col(row, "car")
            standings.append({
                "position": position,
                "car_number": bib,
                "team_name": get_col(row, "teamname"),
                "class_name": get_col(row, "classname"),
                "nationality": "",
                "car_model": car_model,
                "total_time": self._to_seconds(get_col(row, "totaltime")),
                "gap": self._to_seconds(get_col(row, "gaptime")),
                "gap_text": get_col(row, "gaptime"),
                "diff": None,
                "diff_text": "",
                "laps_completed": (
                    int(get_col(row, "lapcount"))
                    if get_col(row, "lapcount")
                    else None
                ),
                "fastest_lap": self._to_seconds(get_col(row, "bestlaptime")),
                "fastest_lap_no": (
                    int(get_col(row, "bestlaplapnumber"))
                    if get_col(row, "bestlaplapnumber")
                    else None
                ),
                "fastest_lap_speed": self._parse_speed(
                    get_col(row, "bestlapaveragespeed")
                ),
                "pit_stops": 0,
                "is_classified": is_classified,
            })

        return standings, session_name, session_type

    # ── PitStopsCsv ────────────────────────────────────────────────────────

    def _parse_pitstops(self, filepath: str) -> list[dict]:
        """Parse PitStopsCsv.

        Columns: Nr;Driver in;Day time in;Time in;Driver out;
                 Day time out;Time out;Nett Time;Reason;Lap In

        Some rows have empty Driver out (car retired during pit stop).
        """
        pitstops = []
        enc = self._detect_encoding(filepath)

        with open(filepath, newline="", encoding=enc) as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)

        if not rows:
            return pitstops

        for row in rows[1:]:  # skip header
            if not row or len(row) < 7:
                continue

            nr = row[0].strip()
            if not nr or not nr.isdigit():
                continue

            lap_in_str = ""
            if len(row) >= 10:
                lap_in_str = row[9].strip()

            in_lap = int(lap_in_str) if lap_in_str else None
            nett_time = self._to_seconds(row[7].strip()) if row[7].strip() else None

            pitstops.append({
                "car_number": nr,
                "driver_in": row[1].strip() if len(row) > 1 else "",
                "driver_out": row[4].strip() if len(row) > 4 else "",
                "in_lap": in_lap,
                "nett_time": nett_time,
                "time_in": self._to_seconds(row[3].strip()) if len(row) > 3 and row[3].strip() else None,
            })

        return pitstops

    def _assign_driver_names_by_stints(self, laps: list[dict], pitstops: list[dict]) -> None:
        """Assign each lap to the driver active for that stint.

        The lap at which a pit stop occurs stays with the outgoing driver;
        laps after that stop use the incoming driver from the pit stop row.
        """
        by_car: dict[str, list[dict]] = {}
        for lap in laps:
            by_car.setdefault(lap["car_number"], []).append(lap)

        for car_num, car_laps in by_car.items():
            car_laps.sort(key=lambda x: x["lap_number"])
            if not car_laps:
                continue

            current_driver = str(car_laps[0].get("driver_name", "") or "").strip()
            if not current_driver:
                for key in ("driver1", "driver2", "driver3", "driver4"):
                    val = str(car_laps[0].get(key, "") or "").strip()
                    if val:
                        current_driver = val
                        break

            car_pitstops = sorted(
                (
                    p for p in pitstops
                    if str(p.get("car_number", "")) == str(car_num)
                    and p.get("in_lap") is not None
                ),
                key=lambda p: int(p["in_lap"]),
            )

            pit_idx = 0
            for lap in car_laps:
                while pit_idx < len(car_pitstops):
                    pit = car_pitstops[pit_idx]
                    stop_lap = int(pit["in_lap"])
                    if lap["lap_number"] > stop_lap:
                        current_driver = (
                            str(pit.get("driver_in", "") or "").strip()
                            or str(pit.get("driver_out", "") or "").strip()
                            or current_driver
                        )
                        pit_idx += 1
                    else:
                        break

                if current_driver:
                    lap["driver_name"] = current_driver

    def _apply_pitstops(
        self, laps: list[dict], pitstops: list[dict]
    ) -> None:
        """Mark in_lap and out_lap on lap records based on pit stop data.

        Swiss Timing PitStopsCsv gives us the "Lap In" number — this is the
        lap ON WHICH the car entered the pits. The following lap is the
        out-lap (after driving through the pit lane).
        """
        # Build a set of (car_number, in_lap) for quick lookup
        pit_in_laps: set[tuple[str, int]] = set()
        for p in pitstops:
            cn = p["car_number"]
            il = p["in_lap"]
            if cn and il is not None:
                pit_in_laps.add((str(cn), int(il)))

        # Group laps by car
        car_laps: dict[str, list[dict]] = {}
        for l in laps:
            car_laps.setdefault(l["car_number"], []).append(l)

        for car_num, cl in car_laps.items():
            cl.sort(key=lambda x: x["lap_number"])
            for i, l in enumerate(cl):
                lap_no = l["lap_number"]
                # Mark in-lap
                if (str(car_num), lap_no) in pit_in_laps:
                    l["in_lap"] = True
                # Mark out-lap = lap immediately after an in-lap
                if i > 0:
                    prev_lap = cl[i - 1]["lap_number"]
                    if (str(car_num), prev_lap) in pit_in_laps:
                        l["out_lap"] = True

        self._assign_driver_names_by_stints(laps, pitstops)

    def _detect_out_laps(self, laps: list[dict]) -> None:
        """Detect out laps: first lap of each stint."""
        detect_out_laps(laps)

    def _detect_in_laps(self, laps: list[dict]) -> None:
        """Heuristic in-lap detection when no PitStopsCsv is available."""
        detect_in_laps(laps)

    # ── TLWlistMessage ────────────────────────────────────────────────────

    def _parse_tlw(self, filepath: str) -> list[dict]:
        """Parse TLWlistMessage (Track Limit Warnings).

        Columns: Bib;Date & Time;Race time;TL at Turn;Message
        """
        warnings = []
        enc = self._detect_encoding(filepath)

        with open(filepath, newline="", encoding=enc) as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)

        for row in rows[1:]:
            if not row or len(row) < 4:
                continue

            bib = row[0].strip()
            if not bib or not bib.isdigit():
                continue

            race_time = self._to_seconds(row[2].strip())
            turn = row[3].strip() if len(row) > 3 else ""

            warnings.append({
                "car_number": bib,
                "race_time": race_time,
                "turn": turn,
                "message": row[4].strip() if len(row) > 4 else "",
            })

        return warnings

    def _apply_tlw(self, laps: list[dict], warnings: list[dict]) -> None:
        """Match TLW warnings to laps and set track_limit flag."""
        apply_tlw(laps, warnings)

    # ── MessageListCSV ─────────────────────────────────────────────────────

    def _parse_messages(self, filepath: str) -> list[dict]:
        """Parse MessageListCSV (Race Control Messages).

        Columns: TIME;RACE TIME;MESSAGE;(empty)
        """
        msgs = []
        enc = self._detect_encoding(filepath)

        with open(filepath, newline="", encoding=enc) as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)

        for row in rows[1:]:
            if not row or len(row) < 3:
                continue

            time_of_day = row[0].strip() if row[0].strip() else ""
            race_time = row[1].strip() if len(row) > 1 and row[1].strip() else ""
            message = row[3].strip() if len(row) > 3 and row[3].strip() else ""

            # Some message rows have message in column index 2 or 3
            if not message and len(row) > 2:
                message = row[2].strip()

            # Skip separator rows in message list
            if message and not message.startswith("---"):
                msgs.append({
                    "time_of_day": time_of_day,
                    "race_time": self._to_seconds(race_time) if race_time else None,
                    "message": message,
                })

        return msgs

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _compute_session_times(laps: list[dict]) -> None:
        """Calculate session_time for each lap as cumulative elapsed time.

        Swiss Timing CSV doesn't include a session_time column, so it is
        computed by summing lap_times sequentially per car.
        session_time for lap N = sum of lap times for laps 1 through N.
        """
        car_groups: dict[str, list[dict]] = {}
        for lap in laps:
            car_groups.setdefault(lap["car_number"], []).append(lap)

        for car_num, car_laps in car_groups.items():
            car_laps.sort(key=lambda x: x["lap_number"])
            cumulative = 0.0
            for lap in car_laps:
                lt = lap.get("lap_time")
                if lt and lt > 0:
                    cumulative += lt
                lap["session_time"] = cumulative if lt and lt > 0 else None

    def _assign_drivers_and_pits(self, laps: list[dict]) -> None:
        """Assign driver names from Driver1-4 columns.

        For Swiss Timing, pit in/out detection is handled by
        _apply_pitstops() when PitStopsCsv is available.
        This method only sets driver names from the sector data.
        """
        car_groups: dict[str, list[dict]] = {}
        for l in laps:
            car_groups.setdefault(l["car_number"], []).append(l)

        for car_num, car_laps in car_groups.items():
            # Assign the initial stint driver from the first lap's Driver1 field.
            first = car_laps[0]
            initial_driver = ""
            for dk in ["driver1", "driver2", "driver3", "driver4"]:
                dv = first.get(dk, "").strip()
                if dv and dv.lower() != "":
                    initial_driver = dv
                    break

            for l in car_laps:
                if not l.get("driver_name"):
                    l["driver_name"] = initial_driver

    def _build_standings_from_laps(self, laps: list[dict]) -> list[dict]:
        """Build standings from lap data when no ResultListCSV is provided.

        Ranks cars by:
          1. Most laps completed (descending)
          2. Shortest total time (for equal laps)
        """
        car_data: dict[str, dict] = {}

        for l in laps:
            cn = l["car_number"]
            if cn not in car_data:
                car_data[cn] = {
                    "car_number": cn,
                    "total_laps": 0,
                    "best_lap": None,
                    "best_lap_no": None,
                    "fastest_lap_speed": None,
                    "total_time": 0.0,
                    "category": l.get("category", ""),
                    "driver_name": l.get("driver_name", ""),
                }
            cd = car_data[cn]
            cd["total_laps"] = max(cd["total_laps"], l["lap_number"])
            lt = l.get("lap_time")
            if lt and lt > 0:
                cd["total_time"] += lt
                if cd["best_lap"] is None or lt < cd["best_lap"]:
                    cd["best_lap"] = lt
                    cd["best_lap_no"] = l["lap_number"]
                    cd["fastest_lap_speed"] = l.get("speed_trap_4")

        # Sort: most laps first, then shortest total time
        sorted_cars = sorted(
            car_data.values(),
            key=lambda c: (-c["total_laps"], c["total_time"] if c["total_time"] > 0 else float("inf")),
        )

        standings = []
        for pos, cd in enumerate(sorted_cars, 1):
            first_time = sorted_cars[0]["total_time"] if sorted_cars else 0
            gap = (
                cd["total_time"] - first_time
                if cd["total_time"] > 0 and first_time > 0
                else None
            )
            standings.append({
                "position": pos,
                "car_number": cd["car_number"],
                "team_name": "",
                "class_name": cd["category"],
                "nationality": "",
                "car_model": "",
                "total_time": cd["total_time"] if cd["total_time"] > 0 else None,
                "gap": gap,
                "gap_text": "",
                "diff": None,
                "diff_text": "",
                "laps_completed": cd["total_laps"],
                "fastest_lap": cd["best_lap"],
                "fastest_lap_no": cd["best_lap_no"],
                "fastest_lap_speed": cd["fastest_lap_speed"],
                "pit_stops": 0,
                "is_classified": True,
            })

        return standings
