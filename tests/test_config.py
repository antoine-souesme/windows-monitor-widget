# -*- coding: utf-8 -*-
"""Tests of the configuration reading, in particular the migration from the
single metric to the list of metrics."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import config


class ConfigTest(unittest.TestCase):

    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self._home.name

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._previous
        self._home.cleanup()

    def write(self, values):
        os.makedirs(config.config_dir(), exist_ok=True)
        with open(config.config_path(), "w", encoding="utf-8") as handle:
            json.dump(values, handle)

    def test_defaults_when_no_file(self):
        values = config.load()
        self.assertEqual(values["probes"], ["cpu"])
        self.assertFalse(values["compact"])

    def test_reads_the_list_of_metrics(self):
        self.write({"probes": ["ram", "cpu"], "compact": True})
        values = config.load()
        self.assertEqual(values["probes"], ["ram", "cpu"])
        self.assertTrue(values["compact"])

    def test_empty_list_is_kept(self):
        self.write({"probes": []})
        self.assertEqual(config.load()["probes"], [])

    def test_old_single_metric_is_migrated(self):
        self.write({"probe": "ram"})
        self.assertEqual(config.load()["probes"], ["ram"])

    def test_list_wins_over_the_old_key(self):
        self.write({"probe": "ram", "probes": ["cpu"]})
        self.assertEqual(config.load()["probes"], ["cpu"])

    def test_broken_metrics_fall_back_to_defaults(self):
        self.write({"probes": "cpu"})
        self.assertEqual(config.load()["probes"], ["cpu"])

    def test_duplicates_and_non_strings_are_dropped(self):
        self.write({"probes": ["cpu", "cpu", 7, None, "ram"]})
        self.assertEqual(config.load()["probes"], ["cpu", "ram"])

    def test_broken_file_falls_back_to_defaults(self):
        os.makedirs(config.config_dir(), exist_ok=True)
        with open(config.config_path(), "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertEqual(config.load()["probes"], ["cpu"])

    def test_save_then_load(self):
        values = config.load()
        values["probes"] = ["ram"]
        values["compact"] = True
        self.assertTrue(config.save(values))
        reloaded = config.load()
        self.assertEqual(reloaded["probes"], ["ram"])
        self.assertTrue(reloaded["compact"])


if __name__ == "__main__":
    unittest.main()
