# -*- coding: utf-8 -*-
"""Tests of the update check: version comparison and reading of the answer
sent by GitHub. Nothing here touches the network."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import updater


def release(tag, assets):
    """Minimal answer of the GitHub releases endpoint."""
    return json.dumps({
        "tag_name": tag,
        "assets": [{"name": name, "browser_download_url": url}
                   for name, url in assets],
    }).encode("utf-8")


class VersionTest(unittest.TestCase):

    def test_newer_version_wins(self):
        self.assertTrue(updater.is_newer("1.0.4", "1.0.3"))
        self.assertTrue(updater.is_newer("1.1.0", "1.0.9"))
        self.assertTrue(updater.is_newer("2.0", "1.9.9"))

    def test_same_or_older_version_loses(self):
        self.assertFalse(updater.is_newer("1.0.3", "1.0.3"))
        self.assertFalse(updater.is_newer("1.0.2", "1.0.3"))
        self.assertFalse(updater.is_newer("0.9", "1.0.3"))

    def test_shorter_number_is_not_newer(self):
        # 1.0 and 1.0.0 are the same version.
        self.assertFalse(updater.is_newer("1.0", "1.0.0"))
        self.assertTrue(updater.is_newer("1.0.1", "1.0"))

    def test_unreadable_version_is_never_newer(self):
        self.assertFalse(updater.is_newer("", "1.0.3"))
        self.assertFalse(updater.is_newer("latest", "1.0.3"))
        self.assertFalse(updater.is_newer(None, "1.0.3"))


class ReadReleaseTest(unittest.TestCase):

    def test_reads_version_and_installer(self):
        payload = release("v1.0.4", [("setup_1.0.4.exe", "https://x/setup.exe")])
        found = updater.read_release(payload)
        self.assertEqual(found.version, "1.0.4")
        self.assertEqual(found.url, "https://x/setup.exe")

    def test_ignores_the_other_files_of_the_release(self):
        payload = release("v1.0.4", [
            ("notes.txt", "https://x/notes.txt"),
            ("setup_1.0.4.exe", "https://x/setup.exe"),
        ])
        self.assertEqual(updater.read_release(payload).url, "https://x/setup.exe")

    def test_release_without_installer_is_ignored(self):
        payload = release("v1.0.4", [("notes.txt", "https://x/notes.txt")])
        self.assertIsNone(updater.read_release(payload))

    def test_broken_answer_is_ignored(self):
        self.assertIsNone(updater.read_release(b"not json"))
        self.assertIsNone(updater.read_release(b"[]"))
        self.assertIsNone(updater.read_release(b"{}"))
        self.assertIsNone(updater.read_release(json.dumps(
            {"tag_name": "v1.0.4", "assets": "wrong"}).encode("utf-8")))


class ShouldCheckTest(unittest.TestCase):

    def test_first_run_checks(self):
        self.assertTrue(updater.should_check(0.0, now=1000.0))

    def test_waits_a_day_between_two_checks(self):
        day = updater.CHECK_INTERVAL_SECONDS
        self.assertFalse(updater.should_check(1000.0, now=1000.0 + day - 1))
        self.assertTrue(updater.should_check(1000.0, now=1000.0 + day + 1))

    def test_date_in_the_future_checks(self):
        # Clock moved backwards: better one check too many than never again.
        self.assertTrue(updater.should_check(9000.0, now=1000.0))

    def test_unreadable_date_checks(self):
        self.assertTrue(updater.should_check("hier", now=1000.0))
        self.assertTrue(updater.should_check(None, now=1000.0))


if __name__ == "__main__":
    unittest.main()
