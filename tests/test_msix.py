# -*- coding: utf-8 -*-
"""Checks on the Store package manifest: every picture it names exists, and
the executable it starts is the one PyInstaller builds."""

import os
import unittest
from xml.etree import ElementTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSIX = os.path.join(ROOT, "packaging", "msix")
MANIFEST = os.path.join(MSIX, "AppxManifest.xml")

NAMESPACES = {
    "": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
}


class ManifestTest(unittest.TestCase):

    def setUp(self):
        self.tree = ElementTree.parse(MANIFEST)

    def test_logos_exist(self):
        self._assert_picture(self.tree.find(".//Logo", NAMESPACES).text)
        visual = self.tree.find(".//uap:VisualElements", NAMESPACES)
        self._assert_picture(visual.get("Square44x44Logo"))
        self._assert_picture(visual.get("Square150x150Logo"))

    def _assert_picture(self, relative):
        path = os.path.join(MSIX, relative.replace("\\", os.sep))
        self.assertTrue(os.path.exists(path), path)

    def test_version_is_the_placeholder(self):
        # build_msix.ps1 replaces it; a real number here would be forgotten.
        identity = self.tree.find(".//Identity", NAMESPACES)
        self.assertEqual("0.0.0.0", identity.get("Version"))

    def test_executable_matches_the_pyinstaller_name(self):
        application = self.tree.find(".//Application", NAMESPACES)
        self.assertEqual("MonitorWidget.exe", application.get("Executable"))


if __name__ == "__main__":
    unittest.main()
