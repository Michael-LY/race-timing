import unittest
from types import SimpleNamespace

from routes import _calculate_pit_stop_time


class TSLPitStopTimeTestCase(unittest.TestCase):
    def test_uses_time_out_lap_minus_time_in_lap_for_tsl_pitstops(self):
        in_lap = SimpleNamespace(time_in_lap=95.0, time_out_lap=None)
        out_lap = SimpleNamespace(time_in_lap=None, time_out_lap=80.0)

        self.assertEqual(_calculate_pit_stop_time(in_lap, out_lap), 15.0)


if __name__ == "__main__":
    unittest.main()
