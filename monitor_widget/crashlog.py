# -*- coding: utf-8 -*-
"""Log file kept to understand a crash after the fact.

Location: log.txt next to the configuration file. The widget runs without a
console, so without it every error would vanish. It records each start and
each normal exit (a start that follows no exit means the previous run was
cut short), every Python error with its traceback, hard crashes of the
interpreter (faulthandler) and what every thread was doing when the UI
thread stays stuck for more than FREEZE_DELAY seconds.

The file never grows past MAX_SIZE: it is then moved to log.1.txt and a new
one is started, so at most two of them exist. Logging must never be the
cause of a crash: every failure to write is ignored.
"""

import datetime
import faulthandler
import os
import platform
import sys
import threading
import traceback

from . import config
from .version import __version__

MAX_SIZE = 1024 * 1024
# The UI thread ticks every HEARTBEAT ms; silent for FREEZE_DELAY seconds,
# it is considered frozen.
HEARTBEAT = 2000
FREEZE_DELAY = 10

START = "Start"
STOP = "Normal exit"

_lock = threading.RLock()
_file = None
# Traceback text -> number of times seen, so an error repeated on every
# sample does not flood the file.
_seen = {}


def log_path():
    return os.path.join(config.config_dir(), "log.txt")


def _old_path():
    return os.path.join(config.config_dir(), "log.1.txt")


def _timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _last_event(path):
    """START or STOP, whichever of the two was written last, None if neither."""
    try:
        with open(path, "rb") as handle:
            handle.seek(max(0, os.path.getsize(path) - 64 * 1024))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if " {} Monitor Widget ".format(START) in line:
            return START
        if line.endswith(" " + STOP):
            return STOP
    return None


def _open():
    """Open the log for appending, starting a new one when it is too big."""
    global _file
    path = log_path()
    try:
        os.makedirs(config.config_dir(), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) >= MAX_SIZE:
            os.replace(path, _old_path())
        _file = open(path, "a", encoding="utf-8", errors="replace")
        faulthandler.enable(file=_file, all_threads=True)
    except (OSError, ValueError, RuntimeError):
        _file = None


def _rotate_if_needed():
    if _file is None:
        return
    try:
        too_big = _file.tell() >= MAX_SIZE
    except (OSError, ValueError):
        return
    if not too_big:
        return
    # faulthandler holds the file descriptor: release it first.
    faulthandler.cancel_dump_traceback_later()
    faulthandler.disable()
    redirected = sys.stderr is _file
    try:
        _file.close()
    except OSError:
        pass
    _open()
    if redirected:
        sys.stderr = _file


def write(text):
    """Append one timestamped entry (several lines are fine)."""
    with _lock:
        if _file is None:
            return
        try:
            _file.write("{} {}\n".format(_timestamp(), text.rstrip("\n")))
            _file.flush()
        except (OSError, ValueError):
            return
        _rotate_if_needed()


def log_exception(kind, error_type, error, trace):
    """Write an error and its traceback, only counting it once it repeats."""
    text = "".join(traceback.format_exception(error_type, error, trace))
    with _lock:
        count = _seen.get(text, 0) + 1
        _seen[text] = count
    if count == 1:
        write("{}:\n{}".format(kind, text))
    elif count in (10, 100, 1000) or count % 10000 == 0:
        write("{}: same error as above, {} times so far".format(kind, count))


def start():
    """Open the log and catch every error from now on."""
    with _lock:
        previous = _last_event(log_path())
        _open()
    if previous == START:
        write("The previous run ended without a normal exit "
              "(crash, forced close or Windows shutdown)")
    write("{} Monitor Widget {} (Python {}, {} {})".format(
        START, __version__, platform.python_version(), platform.system(),
        platform.release()))
    sys.excepthook = lambda *error: log_exception("Uncaught error", *error)
    threading.excepthook = lambda args: log_exception(
        "Error in thread {}".format(args.thread.name if args.thread else "?"),
        args.exc_type, args.exc_value, args.exc_traceback)
    # Without a console, anything else printed as an error would be lost.
    if sys.stderr is None and _file is not None:
        sys.stderr = _file


def watch(root):
    """Catch the errors of the tkinter callbacks, which do not stop the
    program, and arm the freeze detector on the UI thread."""
    root.report_callback_exception = lambda *error: log_exception(
        "Error in the interface", *error)

    def tick():
        if _file is not None:
            # Re-arming cancels the previous countdown: it only fires when
            # the UI thread stops coming back here.
            faulthandler.dump_traceback_later(FREEZE_DELAY, file=_file)
        root.after(HEARTBEAT, tick)

    tick()


def stop():
    """Note the normal exit and close the log."""
    global _file
    write(STOP)
    with _lock:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        if _file is not None:
            if sys.stderr is _file:
                sys.stderr = None
            try:
                _file.close()
            except OSError:
                pass
        _file = None
        _seen.clear()
