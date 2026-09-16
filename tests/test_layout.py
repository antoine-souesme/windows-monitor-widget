# -*- coding: utf-8 -*-
"""Tests of the height the window needs for the metrics it shows."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import ui


class WindowHeightTest(unittest.TestCase):

    def test_one_metric_keeps_the_historical_height(self):
        self.assertEqual(ui.window_height(1, False), 90)

    def test_each_extra_metric_adds_a_block(self):
        self.assertEqual(ui.window_height(2, False), 170)
        self.assertEqual(ui.window_height(3, False), 250)

    def test_compact_mode_is_much_shorter(self):
        self.assertEqual(ui.window_height(1, True), 46)
        self.assertEqual(ui.window_height(2, True), 78)

    def test_no_metric_shows_the_empty_frame(self):
        self.assertEqual(ui.window_height(0, False), ui.EMPTY_HEIGHT)
        self.assertEqual(ui.window_height(0, True), ui.EMPTY_HEIGHT)


if __name__ == "__main__":
    unittest.main()
