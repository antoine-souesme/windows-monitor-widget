# -*- coding: utf-8 -*-
"""Tests of the metrics: their options, their texts and their scale."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import probes

MEGA = 1024 * 1024


class MemoryTextTest(unittest.TestCase):

    def probe(self, display):
        probe = probes.MemoryProbe()
        probe.configure({"ram_display": display})
        probe._used = 9 * 1024 * MEGA
        probe._total = 16 * 1024 * MEGA
        return probe

    def test_percentage_only(self):
        self.assertEqual(self.probe("percent").texts([62.0]), ["62%"])

    def test_value_only(self):
        self.assertEqual(self.probe("value").texts([62.0]), ["9/16 Go"])

    def test_both(self):
        self.assertEqual(self.probe("both").texts([62.0]), ["62% · 9/16 Go"])

    def test_unknown_total_falls_back_to_the_percentage(self):
        probe = probes.MemoryProbe()
        probe.configure({"ram_display": "value"})
        self.assertEqual(probe.texts([62.0]), ["62%"])


class NetworkTest(unittest.TestCase):

    def probe(self, display="both"):
        probe = probes.NetworkProbe()
        probe.configure({"network_display": display})
        return probe

    def test_both_directions_are_drawn_side_by_side(self):
        self.assertEqual(self.probe().columns(), 2)

    def test_one_direction_takes_the_whole_block(self):
        self.assertEqual(self.probe("upload").columns(), 1)

    def test_the_unit_is_written_once_and_shared(self):
        texts = self.probe().texts((12 * MEGA, 1.5 * MEGA))
        self.assertEqual(texts, ["↓ 12", "↑ 1,5 Mo/s"])

    def test_the_arrow_follows_the_chosen_direction(self):
        self.assertEqual(self.probe("upload").texts((0.0,)), ["↑ 0 Ko/s"])
        self.assertEqual(self.probe("download").texts((0.0,)), ["↓ 0 Ko/s"])

    def test_a_quiet_line_stays_flat(self):
        probe = self.probe("download")
        self.assertEqual(probe.ratio(0.0), 0.0)
        self.assertLess(probe.ratio(1024.0), 0.05)

    def test_the_graph_scales_itself_on_the_last_minute(self):
        probe = self.probe("download")
        for _ in range(60):
            probe._peaks[0].append(10 * MEGA)
        self.assertEqual(probe.ratio(10 * MEGA), 1.0)
        self.assertAlmostEqual(probe.ratio(5 * MEGA), 0.5)

    def test_a_reset_counter_never_gives_a_negative_rate(self):
        probe = self.probe("download")
        probe.start()
        probe._counters = (10 ** 9, 10 ** 9)
        probe._time = probe._time - 1.0
        self.assertGreaterEqual(probe.read()[0], 0.0)


class OptionTest(unittest.TestCase):

    def test_every_option_has_a_default_among_its_choices(self):
        for cls in probes.options():
            for option in cls.options:
                self.assertIn(option.default, option.values())

    def test_the_defaults_are_exposed_to_the_configuration(self):
        defaults = probes.option_defaults()
        self.assertEqual(defaults["ram_display"], "percent")
        self.assertEqual(defaults["network_display"], "both")


if __name__ == "__main__":
    unittest.main()
