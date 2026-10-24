# -*- coding: utf-8 -*-
"""Tests of the custom grid arithmetic: cells, resizing, first fill and
column width."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import config, grid, i18n


class GridTest(unittest.TestCase):

    def test_cell_round_trip(self):
        self.assertEqual(grid.parse(grid.cell_id("net", 1)), ("net", 1))

    def test_bad_cells_are_rejected(self):
        for cell in ("net:9", "nope:0", "cpu", 3, None, "cpu:x"):
            self.assertIsNone(grid.parse(cell))
        self.assertTrue(grid.is_valid(""))

    def test_choices_start_with_empty_and_split_the_network(self):
        i18n.set_language("fr")
        self.addCleanup(i18n.set_language, i18n.DEFAULT)
        choices = grid.choices()
        self.assertEqual(choices[0], ("", "(vide)"))
        self.assertIn(("net:0", "Réseau réception"), choices)
        self.assertIn(("net:1", "Réseau envoi"), choices)

    def test_shrinking_then_growing_keeps_positions(self):
        cells = ["a", "b", "c", "d", "e", "f"]          # 3 columns × 2 rows
        small = grid.resized(cells, 3, 2, 1)
        self.assertEqual(small, ["a", "b"])
        self.assertEqual(grid.resized(small, 2, 3, 2), ["a", "b", "", "", "", ""])

    def test_first_fill_is_one_column(self):
        self.assertEqual(grid.initial(["cpu:0", "net:0", "net:1"]),
                         (1, 3, ["cpu:0", "net:0", "net:1"]))
        self.assertEqual(grid.initial([]), (1, 1, [""]))
        self.assertEqual(grid.initial(["cpu:0"] * 8)[1], 6)

    def test_displayed_cells_follow_the_network_option(self):
        values = dict(config.DEFAULTS, probes=["cpu", "net"], network_display="upload")
        self.assertEqual(grid.displayed_cells(values), ["cpu:0", "net:1"])

    def test_needed_keys_skip_empty_and_repeats(self):
        self.assertEqual(grid.needed_keys(["", "net:1", "cpu:0", "net:0"]), ["net", "cpu"])
        self.assertEqual(grid.needed_keys(["", ""]), [])

    def test_wide_cells_keep_only_what_fits(self):
        # 3 columns × 2 rows: 2 is on the last column, 1 is covered by 0,
        # 6 is outside, True and "4" are no index.
        self.assertEqual(grid.clean_wide([4, 2, 1, 0, 6, True, "4", 0], 3, 2), [0, 4])
        self.assertEqual(grid.clean_wide([0], 1, 3), [])
        self.assertEqual(grid.clean_wide(None, 2, 2), [])

    def test_the_cell_under_a_wide_one_is_emptied(self):
        self.assertEqual(grid.spanned(["a", "b", "c", "d"], [0]), ["a", "", "c", "d"])

    def test_resizing_keeps_wide_cells_in_place(self):
        # 2 columns × 4 rows, the last row wide, as one wide line under
        # three rows of two.
        self.assertEqual(grid.resized_wide([6], 2, 3, 4), [9])
        self.assertEqual(grid.resized_wide([6], 2, 1, 4), [])
        self.assertEqual(grid.resized_wide([6], 2, 2, 3), [])
        self.assertEqual(grid.resized_wide([1], 3, 2, 2), [])

    def test_column_width_fits_the_screen(self):
        self.assertEqual(grid.fit_column_width(300, 6, 1200, 140, 600), 200)
        self.assertEqual(grid.fit_column_width(300, 6, 600, 140, 600), 140)
        self.assertEqual(grid.fit_column_width(900, 1, 3000, 140, 600), 600)


if __name__ == "__main__":
    unittest.main()
