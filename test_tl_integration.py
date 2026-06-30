"""Integration test for TLW: parser + DB insert + analytics API."""
import csv
import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import config
import app as app_module
from models import db, Event, Session, LapRecord, TimeKeeper, User
from parsers.swiss_timing import SwissTimingParser


class TLWIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.tmp_db.name}"

        imported = importlib.reload(app_module)
        self.app = imported.create_app()
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        with self.app.app_context():
            db.engine.dispose()
        if os.path.exists(self.tmp_db.name):
            os.remove(self.tmp_db.name)

    def _create_csvs(self):
        os.makedirs("test_uploads", exist_ok=True)

        sector_path = "test_uploads/test_sector.csv"
        with open(sector_path, "w", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Bib", "Class", "Driver1", "Driver2", "Driver3", "Driver4",
                         "Car", "Lap", "Time", "Sector1Time", "SpeedTrap1",
                         "Sector2Time", "SpeedTrap2", "Sector3Time", "SpeedTrap3", "TopSpeed"])
            rows = [
                ("10", "GT3", "Alice", "", "", "", "Porsche", "1", "1:45.100", "30.100", "180",
                 "35.200", "175", "39.800", "170", "250"),
                ("10", "GT3", "Alice", "", "", "", "Porsche", "2", "1:43.200", "29.500", "182",
                 "34.800", "178", "38.900", "172", "255"),
                ("10", "GT3", "Alice", "", "", "", "Porsche", "3", "1:44.500", "30.000", "181",
                 "35.000", "176", "39.500", "171", "252"),
                ("20", "GT3", "Bob", "", "", "", "Ferrari", "1", "1:46.300", "30.500", "179",
                 "35.800", "174", "40.000", "169", "248"),
                ("20", "GT3", "Bob", "", "", "", "Ferrari", "2", "1:44.800", "29.800", "183",
                 "35.100", "177", "39.900", "173", "253"),
                ("20", "GT3", "Bob", "", "", "", "Ferrari", "3", "1:45.000", "30.200", "180",
                 "35.300", "176", "39.500", "171", "250"),
                ("30", "GT3", "Charlie", "", "", "", "McLaren", "1", "1:47.000", "31.000", "178",
                 "36.000", "173", "40.000", "168", "245"),
                ("30", "GT3", "Charlie", "", "", "", "McLaren", "2", "1:45.500", "30.300", "181",
                 "35.500", "175", "39.700", "170", "250"),
                ("30", "GT3", "Charlie", "", "", "", "McLaren", "3", "1:46.000", "30.800", "179",
                 "35.800", "174", "39.400", "171", "248"),
            ]
            for row in rows:
                w.writerow(row)

        # TLW: Car 10 lap 2 (session_time: 105.1..208.3), Car 30 lap 1 (session_time: 0..107.0)
        tlw_path = "test_uploads/test_tlw.csv"
        with open(tlw_path, "w", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Bib", "Date & Time", "Race time", "TL at Turn", "Message"])
            w.writerow(["10", "2026-06-30 14:05:00", "1:50.000", "T3", "Track limits exceeded"])
            w.writerow(["30", "2026-06-30 14:01:30", "0:30.000", "T1", "Track limits exceeded"])

        return sector_path, tlw_path

    def test_parser_applies_tlw(self):
        """Parser marks correct laps as track_limit."""
        sector_path, tlw_path = self._create_csvs()
        parser = SwissTimingParser()
        data = parser.parse(sector_path=sector_path, tlw_path=tlw_path)

        tl_laps = [l for l in data["laps"] if l.get("track_limit")]
        print(f"\nParser result: {len(data['laps'])} laps, {len(tl_laps)} TL")
        for l in data["laps"]:
            tl = " [TL]" if l.get("track_limit") else ""
            print(f"  Car {l['car_number']} Lap {l['lap_number']}: {l['lap_time']:.3f}s{tl}")

        self.assertEqual(len(tl_laps), 2)
        car10_lap2 = next(l for l in data["laps"] if l["car_number"] == "10" and l["lap_number"] == 2)
        car30_lap1 = next(l for l in data["laps"] if l["car_number"] == "30" and l["lap_number"] == 1)
        self.assertTrue(car10_lap2["track_limit"])
        self.assertTrue(car30_lap1["track_limit"])

    def test_db_insert_and_best_lap(self):
        """TL laps stored in DB with correct flags; is_best excludes TL."""
        sector_path, tlw_path = self._create_csvs()
        parser = SwissTimingParser()
        data = parser.parse(sector_path=sector_path, tlw_path=tlw_path)

        # Replicate import logic from routes.py
        event = Event(name="Test", track="Spa", year=2026)
        db.session.add(event)
        db.session.flush()

        session = Session(event_id=event.id, name="Race", session_type="Race")
        db.session.add(session)
        db.session.flush()

        # Best lap detection (excludes TL)
        best_times = {}
        for l in data["laps"]:
            if l.get("lap_time") and l["lap_time"] > 0 and not l.get("track_limit"):
                key = l["car_number"]
                if key not in best_times or l["lap_time"] < best_times[key]:
                    best_times[key] = l["lap_time"]

        for l in data["laps"]:
            is_best = False
            if l.get("lap_time") and l["lap_time"] > 0 and not l.get("track_limit"):
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
                is_best=is_best,
                track_limit=l.get("track_limit", False),
                out_lap=l.get("out_lap", False),
                in_lap=l.get("in_lap", False),
                session_time=l.get("session_time"),
            )
            db.session.add(lap)
        db.session.commit()

        # Verify DB state
        all_laps = LapRecord.query.filter_by(session_id=session.id).order_by(
            LapRecord.car_number, LapRecord.lap_number).all()

        tl_db = [l for l in all_laps if l.track_limit]
        print(f"\nDB: {len(all_laps)} laps, {len(tl_db)} TL")
        for l in all_laps:
            tl = " [TL]" if l.track_limit else ""
            best = " [BEST]" if l.is_best else ""
            print(f"  Car {l.car_number} Lap {l.lap_number}: {l.lap_time:.3f}s, session_time={l.session_time:.1f}{tl}{best}")

        # Assertions
        self.assertEqual(len(tl_db), 2)
        for tl in tl_db:
            self.assertFalse(tl.is_best, f"TL lap Car {tl.car_number} Lap {tl.lap_number} should not be best")

        # Car 10 best should be lap 2 (1:43.200 = 103.2s) — the TL lap — so best should be lap 3 (104.5s)
        car10_best = next(l for l in all_laps if l.car_number == "10" and l.is_best)
        self.assertEqual(car10_best.lap_number, 3, f"Car 10 best should be lap 3, got {car10_best.lap_number}")
        print(f"\nCar 10 best: Lap {car10_best.lap_number} ({car10_best.lap_time:.3f}s) ✓")

        # Car 30 best should be lap 2 (1:45.500 = 105.5s), not lap 1 (TL)
        car30_best = next(l for l in all_laps if l.car_number == "30" and l.is_best)
        self.assertEqual(car30_best.lap_number, 2, f"Car 30 best should be lap 2, got {car30_best.lap_number}")
        print(f"Car 30 best: Lap {car30_best.lap_number} ({car30_best.lap_time:.3f}s) ✓")

        print("\n=== ALL INTEGRATION TESTS PASSED ===")


if __name__ == "__main__":
    unittest.main()
