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

    def test_compact_mode_is_shorter(self):
        self.assertEqual(ui.window_height(1, True), 54)
        self.assertEqual(ui.window_height(2, True), 94)

    def test_no_metric_shows_the_empty_frame(self):
        self.assertEqual(ui.window_height(0, False), ui.EMPTY_HEIGHT)
        self.assertEqual(ui.window_height(0, True), ui.EMPTY_HEIGHT)


class ColumnTest(unittest.TestCase):

    def test_one_value_takes_the_whole_width(self):
        self.assertEqual(ui.columns(10, 190, 1), [(10, 190)])

    def test_two_values_share_it_with_a_gap(self):
        left, right = ui.columns(10, 190, 2)
        self.assertEqual(left[0], 10)
        self.assertEqual(right[1], 190)
        self.assertEqual(right[0] - left[1], ui.COLUMN_GAP)
        self.assertEqual(left[1] - left[0], right[1] - right[0])


class ResizeTest(unittest.TestCase):

    def test_pointer_near_an_edge_grabs_it(self):
        self.assertEqual(ui.resize_edge(2, 200), "left")
        self.assertEqual(ui.resize_edge(197, 200), "right")
        self.assertIsNone(ui.resize_edge(100, 200))

    def test_right_edge_keeps_the_left_side_in_place(self):
        self.assertEqual(ui.resized("right", 50, 200, 40), (50, 240))

    def test_left_edge_keeps_the_right_side_in_place(self):
        self.assertEqual(ui.resized("left", 50, 200, -40), (10, 240))
        self.assertEqual(ui.resized("left", 50, 200, 30), (80, 170))

    def test_width_stays_within_bounds(self):
        self.assertEqual(ui.resized("right", 50, 200, 1000), (50, ui.config.MAX_WIDTH))
        self.assertEqual(ui.resized("right", 50, 200, -1000), (50, ui.config.MIN_WIDTH))
        x, width = ui.resized("left", 50, 200, 1000)
        self.assertEqual((x + width, width), (250, ui.config.MIN_WIDTH))

    def test_numbers_do_not_grow_with_the_window(self):
        self.assertEqual(ui.text_room(600), ui.text_room(ui.config.DEFAULTS["width"]))
        self.assertLess(ui.text_room(140), ui.text_room(200))


class EasingTest(unittest.TestCase):

    def test_gauge_moves_towards_the_value(self):
        self.assertTrue(0.0 < ui.eased(0.0, 1.0) < 1.0)
        self.assertTrue(0.0 < ui.eased(1.0, 0.0) < 1.0)

    def test_gauge_settles_on_the_value(self):
        shown = 0.0
        for _ in range(100):
            shown = ui.eased(shown, 0.73)
        self.assertEqual(shown, 0.73)


if __name__ == "__main__":
    unittest.main()
