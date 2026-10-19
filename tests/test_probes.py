# -*- coding: utf-8 -*-
"""Tests of the metrics: their options, their texts and their scale. The
texts are checked in French unless a test says otherwise."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import config, i18n, probes

MEGA = 1024 * 1024


def setUpModule():
    i18n.set_language("fr")


def tearDownModule():
    i18n.set_language(i18n.DEFAULT)


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

    def test_the_template_is_never_narrower_than_the_text(self):
        for display in ("percent", "value", "both"):
            probe = self.probe(display)
            self.assertGreaterEqual(len(probe.template()),
                                    len(probe.texts([62.0])[0]))

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

    def test_both_figures_carry_the_shared_unit(self):
        texts = self.probe().texts((12 * MEGA, 1.5 * MEGA))
        self.assertEqual(texts, ["12 Mo/s", "1,5 Mo/s"])

    def test_the_arrow_is_a_prefix_of_its_own(self):
        self.assertEqual(self.probe().prefixes(), ["↓", "↑"])
        self.assertEqual(self.probe("upload").prefixes(), ["↑"])
        self.assertEqual(self.probe("download").prefixes(), ["↓"])
        self.assertEqual(self.probe("upload").texts((0.0,)), ["0 Ko/s"])

    def test_each_direction_has_a_caption_of_its_own(self):
        self.assertEqual(self.probe().captions(), ["↓ Réception", "↑ Envoi"])
        self.assertEqual(self.probe("upload").captions(), ["↑ Envoi"])

    def test_the_font_is_measured_on_a_fixed_template(self):
        self.assertEqual(self.probe().template(), "99,9 Mo/s")

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


class GpuTest(unittest.TestCase):

    ENGINE_3D = "luid_0x00000000_0x0000D1B5_phys_0_eng_0_engtype_3D"
    ENGINE_VIDEO = "luid_0x00000000_0x0000D1B5_phys_0_eng_3_engtype_VideoDecode"

    def test_the_processes_of_one_engine_add_up(self):
        samples = [("pid_10_" + self.ENGINE_3D, 20.0),
                   ("pid_42_" + self.ENGINE_3D, 15.0),
                   ("pid_10_" + self.ENGINE_VIDEO, 30.0)]
        self.assertEqual(probes.busiest_engine(samples), 35.0)

    def test_the_busiest_engine_wins(self):
        samples = [("pid_10_" + self.ENGINE_3D, 5.0),
                   ("pid_10_" + self.ENGINE_VIDEO, 60.0)]
        self.assertEqual(probes.busiest_engine(samples), 60.0)

    def test_the_value_never_goes_past_a_hundred(self):
        samples = [("pid_1_" + self.ENGINE_3D, 70.0),
                   ("pid_2_" + self.ENGINE_3D, 50.0)]
        self.assertEqual(probes.busiest_engine(samples), 100.0)

    def test_no_engine_reads_as_idle(self):
        self.assertEqual(probes.busiest_engine([]), 0.0)

    def test_an_unavailable_counter_reads_as_idle(self):
        probe = probes.GpuProbe()
        probe._query = None
        self.assertEqual(probe.read(), 0.0)


class GpuTemperatureTest(unittest.TestCase):

    def test_the_temperature_is_written_in_degrees(self):
        self.assertEqual(probes.GpuTemperatureProbe().texts([64.4]), ["64°C"])

    def test_no_reading_is_written_as_a_dash(self):
        self.assertEqual(probes.GpuTemperatureProbe().texts([0.0]), ["–"])

    def test_an_unavailable_card_reads_zero(self):
        probe = probes.GpuTemperatureProbe()
        probe._adapters = None
        self.assertEqual(probe.read(), 0.0)

    def test_the_scale_goes_from_idle_to_throttling(self):
        probe = probes.GpuTemperatureProbe()
        self.assertEqual(probe.ratio(20.0), 0.0)
        self.assertEqual(probe.ratio(100.0), 1.0)
        self.assertGreater(probe.ratio(80.0), probe.ratio(50.0))


class EnglishTest(unittest.TestCase):

    def setUp(self):
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "fr")

    def test_units_and_decimal_point(self):
        probe = probes.NetworkProbe()
        probe.configure({"network_display": "both"})
        self.assertEqual(probe.texts((12 * MEGA, 1.5 * MEGA)),
                         ["12 MB/s", "1.5 MB/s"])
        self.assertEqual(probe.template(), "99.9 MB/s")

    def test_captions_and_slots(self):
        probe = probes.NetworkProbe()
        probe.configure({"network_display": "both"})
        self.assertEqual(probe.captions(), ["↓ Download", "↑ Upload"])
        self.assertEqual(probes.NetworkProbe.slots(),
                         ["Network download", "Network upload"])
        self.assertEqual(probes.GpuTemperatureProbe.slots(), ["GPU temp"])

    def test_memory_value(self):
        probe = probes.MemoryProbe()
        probe.configure({"ram_display": "value"})
        probe._used = 9 * 1024 * MEGA
        probe._total = 16 * 1024 * MEGA
        self.assertEqual(probe.texts([62.0]), ["9/16 GB"])

    def test_every_option_choice_is_translated(self):
        for cls in probes.options():
            for option in cls.options:
                for _value, name in option.choices:
                    self.assertIn(name, i18n.ENGLISH)


class OptionTest(unittest.TestCase):

    def test_every_option_has_a_default_among_its_choices(self):
        for cls in probes.options():
            for option in cls.options:
                self.assertIn(option.default, option.values())

    def test_the_defaults_are_exposed_to_the_configuration(self):
        defaults = probes.option_defaults()
        self.assertEqual(defaults["ram_display"], "percent")
        self.assertEqual(defaults["network_display"], "both")


class SlotTest(unittest.TestCase):

    def test_single_value_metric_has_one_slot(self):
        self.assertEqual(probes.CpuProbe.slots(), ["CPU"])

    def test_network_lists_both_directions(self):
        self.assertEqual(probes.NetworkProbe.slots(),
                         ["Réseau réception", "Réseau envoi"])

    def test_custom_mode_forces_both_directions(self):
        values = {"network_display": "upload"}
        self.assertEqual(probes.configured_values(values, True)["network_display"], "both")
        self.assertEqual(probes.configured_values(values, False)["network_display"], "upload")
        self.assertEqual(values["network_display"], "upload")

    def test_forced_options_are_hidden(self):
        self.assertIn("network_display", probes.custom_hidden_options())
        self.assertNotIn("ram_display", probes.custom_hidden_options())

    def test_every_metric_has_as_many_slots_as_columns_in_custom_mode(self):
        for cls in probes.PROBES.values():
            probe = cls()
            probe.configure(probes.configured_values(config.DEFAULTS, True))
            self.assertEqual(probe.columns(), len(cls.slots()))


if __name__ == "__main__":
    unittest.main()
