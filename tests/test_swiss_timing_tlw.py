import unittest

from parsers.swiss_timing import SwissTimingParser


class SwissTimingTLWTestCase(unittest.TestCase):
    def setUp(self):
        self.parser = SwissTimingParser()

    def test_tlw_marks_correct_lap(self):
        """TLW warning matched to the lap containing its race_time."""
        laps = [
            {"car_number": "10", "lap_number": 1, "lap_time": 100.0, "session_time": 100.0},
            {"car_number": "10", "lap_number": 2, "lap_time": 95.0, "session_time": 195.0},
            {"car_number": "10", "lap_number": 3, "lap_time": 98.0, "session_time": 293.0},
        ]
        warnings = [
            {"car_number": "10", "race_time": 150.0, "turn": "T3", "message": "TL"},
        ]
        self.parser._apply_tlw(laps, warnings)

        self.assertFalse(laps[0].get("track_limit"))
        self.assertTrue(laps[1].get("track_limit"))
        self.assertFalse(laps[2].get("track_limit"))

    def test_tlw_first_lap_match(self):
        """TLW with race_time within first lap."""
        laps = [
            {"car_number": "20", "lap_number": 1, "lap_time": 100.0, "session_time": 100.0},
            {"car_number": "20", "lap_number": 2, "lap_time": 95.0, "session_time": 195.0},
        ]
        warnings = [
            {"car_number": "20", "race_time": 50.0, "turn": "T1", "message": "TL"},
        ]
        self.parser._apply_tlw(laps, warnings)

        self.assertTrue(laps[0].get("track_limit"))
        self.assertFalse(laps[1].get("track_limit"))

    def test_tlw_multiple_warnings_same_car(self):
        """Multiple TLW warnings for the same car."""
        laps = [
            {"car_number": "30", "lap_number": 1, "lap_time": 100.0, "session_time": 100.0},
            {"car_number": "30", "lap_number": 2, "lap_time": 95.0, "session_time": 195.0},
            {"car_number": "30", "lap_number": 3, "lap_time": 98.0, "session_time": 293.0},
        ]
        warnings = [
            {"car_number": "30", "race_time": 50.0, "turn": "T1", "message": "TL"},
            {"car_number": "30", "race_time": 250.0, "turn": "T5", "message": "TL"},
        ]
        self.parser._apply_tlw(laps, warnings)

        self.assertTrue(laps[0].get("track_limit"))
        self.assertFalse(laps[1].get("track_limit"))
        self.assertTrue(laps[2].get("track_limit"))

    def test_tlw_different_cars(self):
        """TLW warnings for different cars don't cross-match."""
        laps = [
            {"car_number": "10", "lap_number": 1, "lap_time": 100.0, "session_time": 100.0},
            {"car_number": "20", "lap_number": 1, "lap_time": 105.0, "session_time": 105.0},
        ]
        warnings = [
            {"car_number": "10", "race_time": 50.0, "turn": "T1", "message": "TL"},
        ]
        self.parser._apply_tlw(laps, warnings)

        self.assertTrue(laps[0].get("track_limit"))
        self.assertFalse(laps[1].get("track_limit"))

    def test_tlw_exceeding_all_session_times(self):
        """TLW with race_time beyond all session_times matches last lap."""
        laps = [
            {"car_number": "40", "lap_number": 1, "lap_time": 100.0, "session_time": 100.0},
            {"car_number": "40", "lap_number": 2, "lap_time": 95.0, "session_time": 195.0},
        ]
        warnings = [
            {"car_number": "40", "race_time": 500.0, "turn": "T9", "message": "TL"},
        ]
        self.parser._apply_tlw(laps, warnings)

        self.assertFalse(laps[0].get("track_limit"))
        self.assertTrue(laps[1].get("track_limit"))

    def test_tlw_empty_warnings(self):
        """No warnings should not modify any laps."""
        laps = [
            {"car_number": "50", "lap_number": 1, "lap_time": 100.0, "session_time": 100.0},
        ]
        self.parser._apply_tlw(laps, [])

        self.assertFalse(laps[0].get("track_limit"))


class SwissTimingOutLapDetectionTestCase(unittest.TestCase):
    def setUp(self):
        self.parser = SwissTimingParser()

    def test_duplicate_lap1_marks_first_as_out_lap(self):
        """Two Lap 1 entries: first is out lap."""
        laps = [
            {"car_number": "74", "lap_number": 1, "lap_time": 136.589},
            {"car_number": "74", "lap_number": 1, "lap_time": 139.669},
            {"car_number": "74", "lap_number": 2, "lap_time": 139.359},
        ]
        self.parser._detect_out_laps(laps)

        self.assertTrue(laps[0].get("out_lap"))
        self.assertFalse(laps[1].get("out_lap"))
        self.assertFalse(laps[2].get("out_lap"))

    def test_no_duplicates_no_out_laps(self):
        """Normal lap sequence: no out laps detected."""
        laps = [
            {"car_number": "10", "lap_number": 1, "lap_time": 105.0},
            {"car_number": "10", "lap_number": 2, "lap_time": 103.0},
            {"car_number": "10", "lap_number": 3, "lap_time": 104.0},
        ]
        self.parser._detect_out_laps(laps)

        self.assertFalse(laps[0].get("out_lap"))
        self.assertFalse(laps[1].get("out_lap"))
        self.assertFalse(laps[2].get("out_lap"))

    def test_out_lap_detection_is_per_car(self):
        """Duplicate Lap 1 in one car doesn't affect another car."""
        laps = [
            {"car_number": "74", "lap_number": 1, "lap_time": 136.0},
            {"car_number": "74", "lap_number": 1, "lap_time": 139.0},
            {"car_number": "10", "lap_number": 1, "lap_time": 105.0},
            {"car_number": "10", "lap_number": 2, "lap_time": 103.0},
        ]
        self.parser._detect_out_laps(laps)

        car74 = [l for l in laps if l["car_number"] == "74"]
        car10 = [l for l in laps if l["car_number"] == "10"]
        self.assertTrue(car74[0].get("out_lap"))
        self.assertFalse(car74[1].get("out_lap"))
        self.assertFalse(car10[0].get("out_lap"))
        self.assertFalse(car10[1].get("out_lap"))


class SwissTimingInLapDetectionTestCase(unittest.TestCase):
    def setUp(self):
        self.parser = SwissTimingParser()

    def test_slow_lap_marked_as_in_lap(self):
        """Lap with time > 1.2x median is flagged as in_lap."""
        laps = [
            {"car_number": "50", "lap_number": 1, "lap_time": 140.0},
            {"car_number": "50", "lap_number": 2, "lap_time": 139.0},
            {"car_number": "50", "lap_number": 3, "lap_time": 138.0},
            {"car_number": "50", "lap_number": 4, "lap_time": 170.0},  # > 139 * 1.2 = 166.8
        ]
        self.parser._detect_in_laps(laps)

        self.assertFalse(laps[0].get("in_lap"))
        self.assertFalse(laps[1].get("in_lap"))
        self.assertFalse(laps[2].get("in_lap"))
        self.assertTrue(laps[3]["in_lap"])

    def test_first_lap_never_in_lap(self):
        """First lap is never flagged as in_lap even if slow."""
        laps = [
            {"car_number": "60", "lap_number": 1, "lap_time": 200.0},
            {"car_number": "60", "lap_number": 2, "lap_time": 139.0},
        ]
        self.parser._detect_in_laps(laps)

        self.assertFalse(laps[0].get("in_lap"))
        self.assertFalse(laps[1].get("in_lap"))

    def test_few_laps_no_detection(self):
        """Less than 2 clean laps: no in_lap detection."""
        laps = [
            {"car_number": "70", "lap_number": 1, "lap_time": 140.0},
            {"car_number": "70", "lap_number": 2, "lap_time": 170.0},
        ]
        self.parser._detect_in_laps(laps)

        self.assertFalse(laps[0].get("in_lap"))
        self.assertFalse(laps[1].get("in_lap"))

    def test_in_lap_detection_is_per_car(self):
        """In lap detection in one car doesn't affect another."""
        laps = [
            {"car_number": "50", "lap_number": 1, "lap_time": 140.0},
            {"car_number": "50", "lap_number": 2, "lap_time": 139.0},
            {"car_number": "50", "lap_number": 3, "lap_time": 170.0},
            {"car_number": "60", "lap_number": 1, "lap_time": 140.0},
            {"car_number": "60", "lap_number": 2, "lap_time": 139.0},
        ]
        self.parser._detect_in_laps(laps)

        car50_lap3 = next(l for l in laps if l["car_number"] == "50" and l["lap_number"] == 3)
        car60_lap1 = next(l for l in laps if l["car_number"] == "60" and l["lap_number"] == 1)
        car60_lap2 = next(l for l in laps if l["car_number"] == "60" and l["lap_number"] == 2)
        self.assertTrue(car50_lap3.get("in_lap"))
        self.assertFalse(car60_lap1.get("in_lap"))
        self.assertFalse(car60_lap2.get("in_lap"))


if __name__ == "__main__":
    unittest.main()
