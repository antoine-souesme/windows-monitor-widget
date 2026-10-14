# -*- coding: utf-8 -*-
"""Everything Windows specific: single instance, window styles, connected
displays and auto start.

Every function stays callable outside Windows (doing nothing useful, but not
failing), so the rest of the program can be read and tested elsewhere.
"""

import ctypes
import os
import sys

IS_WINDOWS = sys.platform.startswith("win")

# Handle kept alive for the whole run of the program.
_lock = None

# Win32 constants.
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080   # hidden from the taskbar and from Alt+Tab
_WS_EX_NOACTIVATE = 0x08000000   # never takes the focus
_WS_EX_APPWINDOW = 0x00040000
_MONITOR_DEFAULTTONULL = 0
_ERROR_ALREADY_EXISTS = 183


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


# --------------------------------------------------------------------------
# Single instance
# --------------------------------------------------------------------------

def acquire_single_instance():
    """Return True when no other instance is already running.

    A named mutex is used on Windows, a lock file elsewhere.
    """
    global _lock
    if IS_WINDOWS:
        kernel32 = ctypes.windll.kernel32
        _lock = kernel32.CreateMutexW(None, False, "Local\\MonitorWidgetSingleInstance")
        return kernel32.GetLastError() != _ERROR_ALREADY_EXISTS
    try:
        import fcntl
        # Imported here: config needs the metrics, which need this module.
        from . import config
        os.makedirs(config.config_dir(), exist_ok=True)
        _lock = open(os.path.join(config.config_dir(), "lock"), "w")
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (ImportError, OSError):
        return True


# --------------------------------------------------------------------------
# Window style
# --------------------------------------------------------------------------

def window_handle(window):
    """Real Win32 handle of the given tkinter window."""
    identifier = window.winfo_id()
    parent = ctypes.windll.user32.GetParent(identifier)
    return parent or identifier


def apply_tool_window_style(window):
    """Hide the window from the taskbar and Alt+Tab, and keep it from
    stealing the focus when clicked."""
    if not IS_WINDOWS:
        return
    try:
        user32 = ctypes.windll.user32
        handle = window_handle(window)
        read = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        write = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        style = read(handle, _GWL_EXSTYLE)
        style = (style | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE) & ~_WS_EX_APPWINDOW
        write(handle, _GWL_EXSTYLE, style)
        # The new style is only picked up after a hide / show cycle.
        window.withdraw()
        window.deiconify()
    except (AttributeError, OSError):
        pass


def round_corners(window):
    """Ask Windows 11 for rounded corners (ignored elsewhere)."""
    if not IS_WINDOWS:
        return
    try:
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
        preference = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            window_handle(window), 33, ctypes.byref(preference),
            ctypes.sizeof(preference))
    except (AttributeError, OSError):
        pass


# --------------------------------------------------------------------------
# Displays
# --------------------------------------------------------------------------

def is_point_on_screen(x, y, window=None):
    """True when the given point falls on a currently connected display."""
    if IS_WINDOWS:
        try:
            return bool(ctypes.windll.user32.MonitorFromPoint(
                _POINT(int(x), int(y)), _MONITOR_DEFAULTTONULL))
        except (AttributeError, OSError, ValueError):
            return True
    if window is None:
        return True
    return 0 <= x < window.winfo_screenwidth() and 0 <= y < window.winfo_screenheight()


# --------------------------------------------------------------------------
# GPU engines (performance counters, the source of the Task Manager)
# --------------------------------------------------------------------------

_GPU_COUNTER = "\\GPU Engine(*)\\Utilization Percentage"
_PDH_FMT_DOUBLE = 0x00000200
_PDH_FMT_NOCAP100 = 0x00008000
_PDH_MORE_DATA = 0x800007D2
_PDH_CSTATUS_NEW_DATA = 1


class _PdhValue(ctypes.Union):
    _fields_ = [("longValue", ctypes.c_long),
                ("doubleValue", ctypes.c_double),
                ("largeValue", ctypes.c_longlong)]


class _PdhCounterValue(ctypes.Structure):
    _fields_ = [("CStatus", ctypes.c_ulong), ("value", _PdhValue)]


class _PdhCounterItem(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _PdhCounterValue)]


class GpuQuery:
    """Open query on the load of every GPU engine of every process."""

    def __init__(self, pdh, query, counter):
        self._pdh = pdh
        self._query = query
        self._counter = counter


def open_gpu_query():
    """Start watching the GPU engines, or None when that is impossible
    (not Windows, no GPU counters, old Windows version...)."""
    if not IS_WINDOWS:
        return None
    try:
        pdh = ctypes.windll.pdh
        query = ctypes.c_void_p()
        if pdh.PdhOpenQueryW(None, None, ctypes.byref(query)) != 0:
            return None
        counter = ctypes.c_void_p()
        if pdh.PdhAddEnglishCounterW(query, _GPU_COUNTER, None,
                                     ctypes.byref(counter)) != 0:
            pdh.PdhCloseQuery(query)
            return None
        # A rate needs two samples: this first one only sets the reference.
        pdh.PdhCollectQueryData(query)
        return GpuQuery(pdh, query, counter)
    except (AttributeError, OSError):
        return None


def read_gpu_engines(gpu):
    """Load of every (process, engine) pair since the previous call, as a list
    of (instance name, percentage). Empty when nothing can be read."""
    if gpu is None:
        return []
    try:
        pdh = gpu._pdh
        if pdh.PdhCollectQueryData(gpu._query) != 0:
            return []
        size = ctypes.c_ulong(0)
        count = ctypes.c_ulong(0)
        flags = _PDH_FMT_DOUBLE | _PDH_FMT_NOCAP100
        status = pdh.PdhGetFormattedCounterArrayW(
            gpu._counter, flags, ctypes.byref(size), ctypes.byref(count), None)
        if ctypes.c_ulong(status).value != _PDH_MORE_DATA or not size.value:
            return []
        buffer = ctypes.create_string_buffer(size.value)
        if pdh.PdhGetFormattedCounterArrayW(
                gpu._counter, flags, ctypes.byref(size), ctypes.byref(count),
                buffer) != 0:
            return []
        items = ctypes.cast(buffer, ctypes.POINTER(_PdhCounterItem))
        samples = []
        for index in range(count.value):
            item = items[index]
            if item.FmtValue.CStatus > _PDH_CSTATUS_NEW_DATA or not item.szName:
                continue
            samples.append((item.szName, item.FmtValue.value.doubleValue))
        return samples
    except (AttributeError, OSError, ValueError):
        return []


# --------------------------------------------------------------------------
# Auto start (HKCU\...\Run)
# --------------------------------------------------------------------------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "MonitorWidget"


def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def startup_command():
    """Command line written to the registry.

    Once packaged by PyInstaller the executable is self contained; when run
    from the sources we point at pythonw.exe so no console window appears.
    """
    if getattr(sys, "frozen", False):
        return '"{}"'.format(os.path.abspath(sys.executable))
    directory = os.path.dirname(sys.executable)
    pythonw = os.path.join(directory, "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    return '"{}" "{}"'.format(pythonw, script)


def is_startup_enabled():
    """Read the actual value present in the registry."""
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
        return bool(value)
    except OSError:
        return False


def set_startup_enabled(enabled):
    """Add or remove the run key. Return the state actually reached."""
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass
    return is_startup_enabled()


# --------------------------------------------------------------------------
# Store package
# --------------------------------------------------------------------------

_APPMODEL_ERROR_NO_PACKAGE = 15700


def is_packaged():
    """True when the widget runs from an MSIX package (Microsoft Store).

    In that case Windows owns the auto start (declared in the manifest and
    toggled from the system settings), so the matching menu entry is hidden.
    """
    if not IS_WINDOWS:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        length = ctypes.c_uint32(0)
        result = kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        return result != _APPMODEL_ERROR_NO_PACKAGE
    except (AttributeError, OSError):
        return False
