import unittest

from parsers.swiss_timing import SwissTimingParser


class SwissTimingDriverAssignmentTestCase(unittest.TestCase):
    def test_pitstop_driver_switch_is_applied_to_subsequent_laps(self):
        parser = SwissTimingParser()
        laps = [
            {"car_number": "30", "lap_number": 1, "driver_name": "Alice"},
            {"car_number": "30", "lap_number": 2, "driver_name": "Alice"},
            {"car_number": "30", "lap_number": 3, "driver_name": "Alice"},
            {"car_number": "30", "lap_number": 4, "driver_name": "Alice"},
            {"car_number": "30", "lap_number": 5, "driver_name": "Alice"},
        ]
        pitstops = [{"car_number": "30", "driver_in": "Bob", "driver_out": "Alice", "in_lap": 3}]

        parser._assign_driver_names_by_stints(laps, pitstops)

        self.assertEqual([lap["driver_name"] for lap in laps], ["Alice", "Alice", "Alice", "Bob", "Bob"])


if __name__ == "__main__":
    unittest.main()
