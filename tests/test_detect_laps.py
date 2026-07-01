"""Tests for extracted detect_laps functions."""
import unittest

from parsers.detect_laps import detect_out_laps, detect_in_laps, apply_tlw, parse_tlw_file


class DetectOutLapsTestCase(unittest.TestCase):
    def test_no_duplicates_no_out_laps(self):
        laps = [
            {"car_number": "10", "lap_number": 1, "lap_time": 105.0},
            {"car_number": "10", "lap_number": 2, "lap_time": 103.0},
        ]
        detect_out_laps(laps)
        self.assertTrue(laps[0].get("out_lap"))
        self.assertFalse(laps[1].get("out_lap"))

    def test_duplicate_lap_marks_first(self):
        laps = [
            {"car_number": "74", "lap_number": 1, "lap_time": 136.0},
            {"car_number": "74", "lap_number": 1, "lap_time": 139.0},
            {"car_number": "74", "lap_number": 2, "lap_time": 139.0},
        ]
        detect_out_laps(laps)
        self.assertTrue(laps[0]["out_lap"])
        self.assertFalse(laps[1].get("out_lap"))
        self.assertFalse(laps[2].get("out_lap"))

    def test_lap_gap_does_not_mark_out_lap(self):
        laps = [
            {"car_number": "20", "lap_number": 1, "lap_time": 140.0},
            {"car_number": "20", "lap_number": 2, "lap_time": 139.0},
            {"car_number": "20", "lap_number": 5, "lap_time": 141.0},
            {"car_number": "20", "lap_number": 6, "lap_time": 139.0},
        ]
        detect_out_laps(laps)
        self.assertTrue(laps[0].get("out_lap"))   # lap 1
        self.assertFalse(laps[1].get("out_lap"))  # lap 2
        self.assertFalse(laps[2].get("out_lap"))  # lap 5
        self.assertFalse(laps[3].get("out_lap"))  # lap 6

    def test_duplicate_non_lap1_not_marked(self):
        """Duplicate lap 2 (or other) should NOT be marked as out_lap."""
        laps = [
            {"car_number": "30", "lap_number": 1, "lap_time": 140.0},
            {"car_number": "30", "lap_number": 2, "lap_time": 139.0},
            {"car_number": "30", "lap_number": 2, "lap_time": 138.0},
            {"car_number": "30", "lap_number": 3, "lap_time": 137.0},
        ]
        detect_out_laps(laps)
        self.assertTrue(laps[0].get("out_lap"))    # lap 1
        self.assertFalse(laps[1].get("out_lap"))   # lap 2
        self.assertFalse(laps[2].get("out_lap"))   # lap 2 duplicate
        self.assertFalse(laps[3].get("out_lap"))   # lap 3


class DetectInLapsTestCase(unittest.TestCase):
    def test_slow_lap_marked(self):
        laps = [
            {"car_number": "50", "lap_number": 1, "lap_time": 140.0},
            {"car_number": "50", "lap_number": 2, "lap_time": 139.0},
            {"car_number": "50", "lap_number": 3, "lap_time": 170.0},
            {"car_number": "50", "lap_number": 4, "lap_time": 138.0},
        ]
        detect_in_laps(laps)
        self.assertFalse(laps[0].get("in_lap"))
        self.assertFalse(laps[1].get("in_lap"))
        self.assertTrue(laps[2]["in_lap"])
        self.assertTrue(laps[3]["out_lap"])


class ApplyTlwTestCase(unittest.TestCase):
    def test_match_warning_to_lap(self):
        laps = [
            {"car_number": "10", "lap_number": 1, "session_time": 100.0},
            {"car_number": "10", "lap_number": 2, "session_time": 200.0},
        ]
        warnings = [{"car_number": "10", "race_time": 150.0, "turn": "T3", "message": ""}]
        apply_tlw(laps, warnings)
        self.assertFalse(laps[0].get("track_limit"))
        self.assertTrue(laps[1]["track_limit"])


class ParseTlwFileTestCase(unittest.TestCase):
    def test_parse_valid_tlw(self):
        import tempfile, os
        content = "Bib;Date & Time;Race time;TL at Turn;Message\n10;2026-01-01 12:00:00;1:50.000;T3;TL\n"
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        f.write(content)
        f.close()
        try:
            warnings = parse_tlw_file(f.name)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["car_number"], "10")
            self.assertAlmostEqual(warnings[0]["race_time"], 110.0)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
