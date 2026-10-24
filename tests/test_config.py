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
        self.assertEqual(values["mode"], "normal")
        self.assertFalse(values["smooth"])

    def test_reads_the_list_of_metrics(self):
        self.write({"probes": ["ram", "cpu"], "mode": "compact"})
        values = config.load()
        self.assertEqual(values["probes"], ["ram", "cpu"])
        self.assertEqual(values["mode"], "compact")

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

    def test_metric_options_have_their_default(self):
        values = config.load()
        self.assertEqual(values["ram_display"], "percent")
        self.assertEqual(values["network_display"], "both")

    def test_metric_options_are_read(self):
        self.write({"ram_display": "value", "network_display": "upload"})
        values = config.load()
        self.assertEqual(values["ram_display"], "value")
        self.assertEqual(values["network_display"], "upload")

    def test_unknown_option_falls_back_to_the_default(self):
        self.write({"ram_display": "octets", "network_display": 3})
        values = config.load()
        self.assertEqual(values["ram_display"], "percent")
        self.assertEqual(values["network_display"], "both")

    def test_save_then_load(self):
        values = config.load()
        values["probes"] = ["ram"]
        values["mode"] = "compact"
        self.assertTrue(config.save(values))
        reloaded = config.load()
        self.assertEqual(reloaded["probes"], ["ram"])
        self.assertEqual(reloaded["mode"], "compact")

    def test_mode_defaults_to_normal(self):
        self.assertEqual(config.load()["mode"], "normal")

    def test_old_compact_flag_is_migrated(self):
        self.write({"compact": True})
        self.assertEqual(config.load()["mode"], "compact")

    def test_mode_wins_over_the_old_flag(self):
        self.write({"compact": True, "mode": "custom"})
        self.assertEqual(config.load()["mode"], "custom")

    def test_unknown_mode_falls_back_to_normal(self):
        self.write({"mode": "giant"})
        self.assertEqual(config.load()["mode"], "normal")

    def test_grid_size_is_bounded(self):
        self.write({"grid_columns": 9, "grid_rows": 0})
        values = config.load()
        self.assertEqual((values["grid_columns"], values["grid_rows"]), (6, 1))

    def test_broken_cells_become_empty_and_fit_the_grid(self):
        self.write({"grid_columns": 2, "grid_rows": 2,
                    "grid_cells": ["cpu:0", "net:9", 3, "nope:0", "ram:0"]})
        self.assertEqual(config.load()["grid_cells"], ["cpu:0", "", "", ""])

    def test_wide_cells_are_checked_and_hide_their_neighbour(self):
        self.write({"grid_columns": 2, "grid_rows": 2,
                    "grid_cells": ["cpu:0", "ram:0", "fps:0", "net:0"],
                    "grid_wide": [2, 3, 9]})
        values = config.load()
        self.assertEqual(values["grid_wide"], [2])
        self.assertEqual(values["grid_cells"], ["cpu:0", "ram:0", "fps:0", ""])

    def test_broken_wide_cells_fall_back_to_none(self):
        self.write({"grid_columns": 2, "grid_rows": 1,
                    "grid_cells": ["cpu:0", "ram:0"], "grid_wide": "0"})
        self.assertEqual(config.load()["grid_wide"], [])

    def test_short_cell_list_is_padded(self):
        self.write({"grid_columns": 2, "grid_rows": 1, "grid_cells": ["net:1"]})
        self.assertEqual(config.load()["grid_cells"], ["net:1", ""])

    def test_language_and_tray_icon_defaults(self):
        values = config.load()
        self.assertEqual(values["language"], "en")
        self.assertTrue(values["tray_icon"])

    def test_unknown_language_falls_back_to_english(self):
        self.write({"language": "de", "tray_icon": False})
        values = config.load()
        self.assertEqual(values["language"], "en")
        self.assertFalse(values["tray_icon"])

    def test_column_width_is_bounded(self):
        self.write({"grid_column_width": 5})
        self.assertEqual(config.load()["grid_column_width"], config.MIN_WIDTH)


if __name__ == "__main__":
    unittest.main()
