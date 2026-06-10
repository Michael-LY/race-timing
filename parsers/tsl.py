"""TSL Timing parser — handles Classification + Sector Analysis CSV pair."""

import csv
import os
import re
from typing import Any

from .base import BaseParser


class TSLTimingParser(BaseParser):
    """Parses TSL Timing CSV exports.

    Two files expected:
      - Classification:  Pos, No., Name, Class, Nationality, Total Time, Gap, Diff,
                         Laps, Fastest Lap, Fast Lap No., Fast Lap Avg. Speed, Pit Stops
      - Sector Analysis: pos, nr, driver_or_team, out_lap, time_out_lap, in_lap, time_in_lap,
                         time_of_day, lapnumber, laptime, sector_1_time, sector_2_time,
                         sector_3_time, speedTrap_1..4_Speed, class, session_time, driver_name
    """

    name = "TSL Timing"
    description = "TSL Timing — Classification + Sector Analysis CSV pair"

    SESSION_TYPE_KEYWORDS = {
        "Practice": ["practice", "free practice", "fp"],
        "Qualifying": ["qualifying", "qual", "q", "qualification"],
        "Race": ["race", "r"],
        "Paid Test": ["paid test", "paidtest", "paid_test"],
    }

    # ── time parsing ──────────────────────────────────────────────

    @staticmethod
    def _to_seconds(val: str) -> float | None:
        if not val or not val.strip():
            return None
        val = val.strip()
        # m:ss.fff
        m = re.fullmatch(r"(\d+):(\d{2})\.(\d+)", val)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 1000
        # ss.fff
        try:
            return float(val)
        except ValueError:
            return None

    @staticmethod
    def _parse_speed(val: str) -> float | None:
        """Parse speed string like '202.62 km/h' or '225.94'."""
        if not val or not val.strip():
            return None
        val = val.strip()
        m = re.match(r"([\d.]+)", val)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_bool(val: str) -> bool:
        return val.strip().upper() == "TRUE"

    # ── session-type detection ────────────────────────────────────

    def _detect_session_type(self, filepath: str) -> str:
        name = os.path.basename(filepath).lower()
        for stype, keywords in self.SESSION_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in name:
                    return stype
        return "Practice"

    # ── detect ────────────────────────────────────────────────────

    def detect(self, filepath: str) -> bool:
        """Return True if this looks like a TSL Classification or Sector Analysis CSV."""
        try:
            with open(filepath, newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header = [h.lower().strip() for h in next(reader)]
            # Classification header check
            if "pos" in header and "no." in header and "total time" in header:
                return True
            # Sector Analysis header check
            if "sector_1_time" in header and "laptime" in header:
                return True
            return False
        except Exception:
            return False

    # ── parse ─────────────────────────────────────────────────────

    def parse(self, classification_path: str = None, sector_path: str = None) -> dict[str, Any]:
        """Parse one or both TSL CSV files.

        Pass paths as keyword arguments. At least one must be provided.
        Returns:
            session_name, session_type, laps (list), standings (list)
        """
        result: dict[str, Any] = {
            "session_name": "",
            "session_type": "Practice",
            "laps": [],
            "standings": [],
        }

        if classification_path:
            standings, cls_name, cls_type = self._parse_classification(classification_path)
            result["standings"] = standings
            result["session_name"] = cls_name or result["session_name"]
            result["session_type"] = cls_type or result["session_type"]

        if sector_path:
            laps, sec_name, sec_type = self._parse_sector_analysis(sector_path)
            result["laps"] = laps
            result["session_name"] = sec_name or result["session_name"]
            result["session_type"] = sec_type or result["session_type"]

        if not result["session_name"]:
            result["session_name"] = result["session_type"]

        return result

    # ── Classification ────────────────────────────────────────────

    def _parse_classification(self, filepath: str) -> tuple[list[dict], str, str]:
        standings = []
        session_name = ""
        session_type = self._detect_session_type(filepath)

        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return [], session_name, session_type

        # Find header row
        header_idx = 0
        for i, row in enumerate(rows):
            if not row:
                continue
            h = [c.lower().strip() for c in row]
            if "pos" in h and ("no." in h or "no" in h):
                header_idx = i
                break

        # Column indices from header
        h = [c.lower().strip() for c in rows[header_idx]]
        col = {}
        for idx, name in enumerate(h):
            col[name] = idx

        def get_col(row, *aliases):
            for alias in aliases:
                if alias in col and col[alias] < len(row):
                    return row[col[alias]].strip()
            return ""

        # Session name from rows above header
        for i in range(header_idx):
            line = " ".join(str(c).strip() for c in rows[i] if str(c).strip())
            if line and not session_name:
                session_name = line
        if not session_name:
            session_name = session_type

        # Parse
        for row in rows[header_idx + 1:]:
            if not row or all(c.strip() == "" for c in row):
                continue

            pos_str = get_col(row, "pos")
            car_no = get_col(row, "no.", "no")
            if not car_no:
                continue

            is_classified = True
            try:
                pos = int(pos_str)
            except ValueError:
                pos = 0
                if pos_str.upper() == "NC":
                    is_classified = False

            standings.append({
                "position": pos,
                "car_number": car_no,
                "team_name": get_col(row, "name"),
                "class_name": get_col(row, "class"),
                "nationality": get_col(row, "nationality"),
                "total_time": self._to_seconds(get_col(row, "total time")),
                "gap": self._to_seconds(get_col(row, "gap")),
                "diff": self._to_seconds(get_col(row, "diff")),
                "laps_completed": int(get_col(row, "laps")) if get_col(row, "laps") else None,
                "fastest_lap": self._to_seconds(get_col(row, "fastest lap")),
                "fastest_lap_no": int(get_col(row, "fast lap no.")) if get_col(row, "fast lap no.") else None,
                "fastest_lap_speed": self._parse_speed(get_col(row, "fast lap avg. speed")),
                "pit_stops": int(get_col(row, "pit stops")) if get_col(row, "pit stops") else 0,
                "is_classified": is_classified,
            })

        return standings, session_name, session_type

    # ── Sector Analysis ───────────────────────────────────────────

    def _parse_sector_analysis(self, filepath: str) -> tuple[list[dict], str, str]:
        laps = []
        session_name = ""
        session_type = self._detect_session_type(filepath)

        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return [], session_name, session_type

        # Find header row
        header_idx = 0
        for i, row in enumerate(rows):
            if not row:
                continue
            h = [c.lower().strip() for c in row]
            if "nr" in h and "laptime" in h and "sector_1_time" in h:
                header_idx = i
                break

        h = [c.lower().strip() for c in rows[header_idx]]
        col = {}
        for idx, name in enumerate(h):
            col[name] = idx

        def get_col(row, *aliases):
            for alias in aliases:
                if alias in col and col[alias] < len(row):
                    return row[col[alias]].strip()
            return ""

        # Session name
        for i in range(header_idx):
            line = " ".join(str(c).strip() for c in rows[i] if str(c).strip())
            if line and not session_name:
                session_name = line
        if not session_name:
            session_name = session_type

        # Parse
        for row in rows[header_idx + 1:]:
            if not row or all(c.strip() == "" for c in row):
                continue

            car_no = get_col(row, "nr")
            lap_str = get_col(row, "lapnumber")
            if not car_no or not lap_str:
                continue
            try:
                lap_number = int(lap_str)
            except ValueError:
                continue

            laps.append({
                "car_number": car_no,
                "driver_name": get_col(row, "driver_name"),
                "category": get_col(row, "class"),
                "lap_number": lap_number,
                "lap_time": self._to_seconds(get_col(row, "laptime")),
                "sector_1": self._to_seconds(get_col(row, "sector_1_time")),
                "sector_2": self._to_seconds(get_col(row, "sector_2_time")),
                "sector_3": self._to_seconds(get_col(row, "sector_3_time")),
                "speed_trap_1": self._parse_speed(get_col(row, "speedtrap_1_speed")),
                "speed_trap_2": self._parse_speed(get_col(row, "speedtrap_2_speed")),
                "speed_trap_3": self._parse_speed(get_col(row, "speedtrap_3_speed")),
                "speed_trap_4": self._parse_speed(get_col(row, "speedtrap_4_speed")),
                "time_of_day": get_col(row, "time_of_day"),
                "session_time": self._to_seconds(get_col(row, "session_time")),
                "out_lap": self._parse_bool(get_col(row, "out_lap")),
                "in_lap": self._parse_bool(get_col(row, "in_lap")),
                "position": int(get_col(row, "pos")) if get_col(row, "pos") else None,
            })

        # Sort by car number then lap number
        laps.sort(key=lambda x: (str(x["car_number"]).zfill(4), x["lap_number"]))

        return laps, session_name, session_type
