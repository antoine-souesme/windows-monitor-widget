# -*- coding: utf-8 -*-
"""Tests of the layouts handed to Windows to read the frame rates: a wrong
size would make Windows read or write past them. The sizes are those of
64 bit Windows, which is what the package is built for."""

import ctypes
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import system


@unittest.skipUnless(ctypes.sizeof(ctypes.c_void_p) == 8, "64 bit layouts")
class LayoutTest(unittest.TestCase):

    def test_trace_layouts_match_windows(self):
        self.assertEqual(ctypes.sizeof(system._TraceProperties), 120)
        self.assertEqual(ctypes.sizeof(system._LogfileHeader), 280)
        self.assertEqual(ctypes.sizeof(system._TraceLogfile), 448)
        self.assertEqual(ctypes.sizeof(system._EventHeader), 80)
        self.assertEqual(ctypes.sizeof(system._EventRecord), 112)

    def test_desktop_timing_matches_windows(self):
        self.assertEqual(ctypes.sizeof(system._DwmTimingInfo), 292)
        self.assertEqual(system._DwmTimingInfo.cFrame.offset, 56)

    def test_providers_are_recognized_by_their_id(self):
        for provider in (system._DXGI, system._D3D9):
            self.assertIn(system._guid(provider).Data1,
                          {data1 for data1, _event in system._PRESENT_EVENTS})


if __name__ == "__main__":
    unittest.main()
