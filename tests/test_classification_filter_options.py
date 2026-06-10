import unittest

from routes import get_classification_filter_options


class DummyStanding:
    def __init__(self, class_name):
        self.class_name = class_name


class ClassificationFilterOptionsTests(unittest.TestCase):
    def test_collects_unique_class_names(self):
        standings = [
            DummyStanding("GT3"),
            DummyStanding("GT4"),
            DummyStanding("GT3"),
            DummyStanding("  "),
        ]

        self.assertEqual(get_classification_filter_options(standings), ["GT3", "GT4"])


if __name__ == "__main__":
    unittest.main()
