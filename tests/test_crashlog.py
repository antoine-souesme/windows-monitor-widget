# -*- coding: utf-8 -*-
"""Tests of the log file: starts and exits, errors, size limit."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import crashlog


def _raise(message):
    try:
        raise ValueError(message)
    except ValueError:
        return sys.exc_info()


class CrashLogTest(unittest.TestCase):

    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self._home.name
        self._hooks = (sys.excepthook, crashlog.threading.excepthook, sys.stderr)

    def tearDown(self):
        crashlog.stop()
        sys.excepthook, crashlog.threading.excepthook, sys.stderr = self._hooks
        if self._previous is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._previous
        self._home.cleanup()

    def read(self):
        with open(crashlog.log_path(), encoding="utf-8") as handle:
            return handle.read()

    def test_a_normal_run_writes_a_start_and_an_exit(self):
        crashlog.start()
        crashlog.stop()
        text = self.read()
        self.assertIn("Start Monitor Widget", text)
        self.assertTrue(text.rstrip().endswith(crashlog.STOP))
        self.assertNotIn("without a normal exit", text)

    def test_a_run_cut_short_is_reported_at_the_next_start(self):
        crashlog.start()
        crashlog.write("working")
        # No stop(): the process died here.
        crashlog._file.close()
        crashlog._file = None
        crashlog.start()
        self.assertIn("without a normal exit", self.read())

    def test_an_error_is_written_with_its_traceback(self):
        crashlog.start()
        crashlog.log_exception("Error in the interface", *_raise("boom"))
        text = self.read()
        self.assertIn("Error in the interface", text)
        self.assertIn("ValueError: boom", text)
        self.assertIn("Traceback", text)

    def test_a_repeated_error_is_only_counted(self):
        crashlog.start()
        error = _raise("again")
        for _ in range(10):
            crashlog.log_exception("Error in the interface", *error)
        text = self.read()
        self.assertEqual(text.count("ValueError: again"), 1)
        self.assertIn("same error as above, 10 times so far", text)

    def test_the_uncaught_errors_end_up_in_the_log(self):
        crashlog.start()
        sys.excepthook(*_raise("uncaught"))
        self.assertIn("ValueError: uncaught", self.read())

    def test_a_full_log_is_moved_aside(self):
        os.makedirs(os.path.dirname(crashlog.log_path()), exist_ok=True)
        with open(crashlog.log_path(), "w", encoding="utf-8") as handle:
            handle.write("x" * crashlog.MAX_SIZE)
        crashlog.start()
        self.assertTrue(os.path.exists(crashlog._old_path()))
        self.assertLess(os.path.getsize(crashlog.log_path()), crashlog.MAX_SIZE)

    def test_the_log_never_grows_past_its_limit_while_running(self):
        crashlog.start()
        line = "y" * 1000
        for _ in range(crashlog.MAX_SIZE // 1000 + 10):
            crashlog.write(line)
        self.assertTrue(os.path.exists(crashlog._old_path()))
        self.assertLess(os.path.getsize(crashlog.log_path()), crashlog.MAX_SIZE)

    def test_an_unwritable_folder_does_not_fail(self):
        os.environ["APPDATA"] = os.path.join(self._home.name, "file")
        open(os.environ["APPDATA"], "w").close()
        crashlog.start()
        crashlog.write("lost")
        crashlog.log_exception("Uncaught error", *_raise("lost"))


if __name__ == "__main__":
    unittest.main()
