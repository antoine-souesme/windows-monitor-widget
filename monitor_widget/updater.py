# -*- coding: utf-8 -*-
"""Looking for a newer release on GitHub, and installing it.

This is the only module talking to the network. Everything here is written to
stay silent when anything goes wrong: no connection, a rewritten answer or a
release without installer simply means "no update found". The check runs in a
background thread, so the window never waits for it.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from .version import __version__

REPOSITORY = "antoine-souesme/windows-widget-monitor"
LATEST_URL = "https://api.github.com/repos/{}/releases/latest".format(REPOSITORY)
USER_AGENT = "MonitorWidget/{}".format(__version__)

CHECK_INTERVAL_SECONDS = 24 * 60 * 60   # at most one check a day
TIMEOUT_SECONDS = 8
MAX_ANSWER_BYTES = 1024 * 1024          # a release description stays small
MAX_INSTALLER_BYTES = 200 * 1024 * 1024

_INSTALLER = re.compile(r"^setup_.*\.exe$", re.IGNORECASE)
_NUMBER = re.compile(r"^\d+(\.\d+)*$")

IS_WINDOWS = sys.platform.startswith("win")


class Release(object):
    """A published version and the installer that comes with it."""

    def __init__(self, version, url):
        self.version = version
        self.url = url


# --------------------------------------------------------------------------
# Version numbers
# --------------------------------------------------------------------------

def _parts(version):
    """Split 1.0.3 into (1, 0, 3), or return None when unreadable."""
    if not isinstance(version, str) or not _NUMBER.match(version.strip()):
        return None
    return tuple(int(piece) for piece in version.strip().split("."))


def is_newer(candidate, current):
    """True when `candidate` is a version number above `current`."""
    left, right = _parts(candidate), _parts(current)
    if left is None or right is None:
        return False
    # 1.0 and 1.0.0 must compare equal, so both are padded to the same length.
    size = max(len(left), len(right))
    left += (0,) * (size - len(left))
    right += (0,) * (size - len(right))
    return left > right


# --------------------------------------------------------------------------
# Reading what GitHub answers
# --------------------------------------------------------------------------

def read_release(payload):
    """Turn the answer of the releases endpoint into a Release, or None."""
    try:
        data = json.loads(payload.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tag = data.get("tag_name")
    if not isinstance(tag, str):
        return None
    version = tag[1:] if tag.startswith("v") else tag
    assets = data.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if isinstance(name, str) and isinstance(url, str) and _INSTALLER.match(name):
            return Release(version, url)
    return None


def should_check(last_check, now=None):
    """True when enough time has passed since the last look at GitHub."""
    if now is None:
        now = time.time()
    try:
        previous = float(last_check)
    except (TypeError, ValueError):
        return True
    if previous <= 0:
        # Never checked yet, which is the state of a fresh install.
        return True
    # A date in the future means the clock moved: check rather than wait.
    return previous > now or now - previous >= CHECK_INTERVAL_SECONDS


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

def _get(url, limit):
    """Download an address, returning None instead of raising."""
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:
            return answer.read(limit)
    except Exception:
        return None


def fetch_release():
    """The published release when it is newer than the running one."""
    payload = _get(LATEST_URL, MAX_ANSWER_BYTES)
    if payload is None:
        return None
    release = read_release(payload)
    if release is None or not is_newer(release.version, __version__):
        return None
    return release


def check_in_background(callback):
    """Look for an update without blocking, then hand the result over.

    `callback` is called with the Release, or with None. It runs on the
    background thread: the window is responsible for coming back to its own
    thread before touching anything on screen.
    """
    def run():
        try:
            callback(fetch_release())
        except Exception:
            pass

    thread = threading.Thread(target=run, name="update-check", daemon=True)
    thread.start()
    return thread


# --------------------------------------------------------------------------
# Installing
# --------------------------------------------------------------------------

def download(release):
    """Save the installer in the temporary folder. Return its path or None."""
    payload = _get(release.url, MAX_INSTALLER_BYTES)
    if not payload:
        return None
    folder = os.path.join(tempfile.gettempdir(), "MonitorWidgetUpdate")
    path = os.path.join(folder, "setup_{}.exe".format(release.version))
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(payload)
    except OSError:
        return None
    return path


def install(path):
    """Start the installer and let it replace the running copy.

    Silent mode, and the installer restarts the widget once it is done. Only
    Windows can do this: elsewhere the file is downloaded but never run.
    """
    if not IS_WINDOWS or not path:
        return False
    try:
        subprocess.Popen([path, "/SILENT", "/NOCANCEL"], close_fds=True)
        return True
    except OSError:
        return False
