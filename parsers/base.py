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
    def parse(self, filepath: str) -> Dict[str, Any]:
        """Parse CSV file and return structured session data.

        Returns dict:
            session_name: str
            session_type: str (Practice/Qualifying/Race)
            laps: list of dicts with keys:
                car_number, driver_name, category, lap_number,
                lap_time, sector_1, sector_2, sector_3, gap, speed, position
        """

    @abstractmethod
    def detect(self, filepath: str) -> bool:
        """Quick check whether CSV matches this parser's format."""
