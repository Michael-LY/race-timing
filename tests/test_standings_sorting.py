import unittest

from routes import sort_standings_for_display


class StandingsSortingTestCase(unittest.TestCase):
    def test_zero_position_entries_are_moved_to_the_bottom(self):
        rows = [
            type("Standing", (), {"car_number": "3", "position": 0, "is_classified": True, "laps_completed": 10})(),
            type("Standing", (), {"car_number": "1", "position": 2, "is_classified": True, "laps_completed": 20})(),
            type("Standing", (), {"car_number": "2", "position": 1, "is_classified": True, "laps_completed": 15})(),
            type("Standing", (), {"car_number": "4", "position": 0, "is_classified": False, "laps_completed": 5})(),
        ]

        sorted_rows = sort_standings_for_display(rows)

        self.assertEqual([row.car_number for row in sorted_rows], ["2", "1", "3", "4"])

    def test_non_classified_rows_without_valid_position_are_kept_last(self):
        rows = [
            type("Standing", (), {"car_number": "1", "position": 5, "is_classified": True, "laps_completed": 10})(),
            type("Standing", (), {"car_number": "2", "position": 0, "is_classified": True, "laps_completed": 20})(),
            type("Standing", (), {"car_number": "3", "position": 0, "is_classified": False, "laps_completed": 15})(),
        ]

        sorted_rows = sort_standings_for_display(rows)

        self.assertEqual([row.car_number for row in sorted_rows], ["1", "2", "3"])

    def test_sort_does_not_mutate_input_objects(self):
        rows = [
            type("Standing", (), {"car_number": "1", "position": 1, "is_classified": True, "laps_completed": 10})(),
            type("Standing", (), {"car_number": "2", "position": 0, "is_classified": True, "laps_completed": 20})(),
        ]

        sort_standings_for_display(rows)

        self.assertTrue(rows[0].is_classified)
        self.assertTrue(rows[1].is_classified)


if __name__ == "__main__":
    unittest.main()
