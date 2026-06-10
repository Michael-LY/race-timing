"""Base parser interface for time keeper CSV files."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseParser(ABC):
    """Abstract base class for time keeper CSV parsers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable parser name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the format this parser handles."""

    @abstractmethod
    def parse(self, **kwargs) -> Dict[str, Any]:
        """Parse CSV file(s) and return structured session data.

        Accepts keyword arguments for file paths. Implementations define
        which files they accept (e.g., sector_path=, classification_path=).

        Returns dict:
            session_name: str
            session_type: str (Practice/Qualifying/Race/Paid Test/Bronze Session/
                               Pre-Qualifying/Warm-up)
            laps: list of dicts with keys:
                car_number, driver_name, category, lap_number,
                lap_time, sector_1, sector_2, sector_3, gap, speed, position,
                out_lap, in_lap, time_of_day, session_time,
                speed_trap_1, speed_trap_2, speed_trap_3, speed_trap_4
            standings: list of dicts with keys:
                position, car_number, team_name, class_name, nationality,
                total_time, gap, diff, laps_completed, fastest_lap,
                fastest_lap_no, fastest_lap_speed, pit_stops, is_classified
        """

    @abstractmethod
    def detect(self, filepath: str) -> bool:
        """Quick check whether CSV matches this parser's format."""
