import unittest
from pathlib import Path


class ChartZoomConfigTestCase(unittest.TestCase):
    def test_chart_templates_include_y_axis_zoom_configuration(self):
        repo_root = Path(__file__).resolve().parents[1]
        base_template = (repo_root / "templates" / "base.html").read_text(encoding="utf-8")
        session_template = (repo_root / "templates" / "session_detail.html").read_text(encoding="utf-8")

        self.assertIn("chartjs-plugin-zoom", base_template)
        self.assertIn("mode: 'y'", session_template)


if __name__ == "__main__":
    unittest.main()
