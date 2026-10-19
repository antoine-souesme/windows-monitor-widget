# -*- coding: utf-8 -*-
"""Everything Windows specific: single instance, window styles, connected
displays, GPU counters, auto start and notification area icon.

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
# GPU temperature (graphics kernel, the other source of the Task Manager)
# --------------------------------------------------------------------------

_KMTQAITYPE_ADAPTERPERFDATA = 62


class _Luid(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_ulong), ("HighPart", ctypes.c_long)]


class _AdapterInfo(ctypes.Structure):
    _fields_ = [("hAdapter", ctypes.c_uint),
                ("AdapterLuid", _Luid),
                ("NumOfSources", ctypes.c_ulong),
                ("bPrecisePresentRegionsPreferred", ctypes.c_int)]


class _EnumAdapters2(ctypes.Structure):
    _fields_ = [("NumAdapters", ctypes.c_ulong),
                ("pAdapters", ctypes.POINTER(_AdapterInfo))]


class _QueryAdapterInfo(ctypes.Structure):
    _fields_ = [("hAdapter", ctypes.c_uint),
                ("Type", ctypes.c_int),
                ("pPrivateDriverData", ctypes.c_void_p),
                ("PrivateDriverDataSize", ctypes.c_uint)]


class _AdapterPerfData(ctypes.Structure):
    _fields_ = [("PhysicalAdapterIndex", ctypes.c_uint32),
                ("MemoryFrequency", ctypes.c_ulonglong),
                ("MaxMemoryFrequency", ctypes.c_ulonglong),
                ("MaxMemoryFrequencyOC", ctypes.c_ulonglong),
                ("MemoryBandwidth", ctypes.c_ulonglong),
                ("PCIEBandwidth", ctypes.c_ulonglong),
                ("FanRPM", ctypes.c_ulong),
                ("Power", ctypes.c_ulong),
                ("Temperature", ctypes.c_ulong),     # tenths of a degree
                ("PowerStateOverride", ctypes.c_ubyte)]


class GpuAdapters:
    """Graphics adapters kept open for the whole run."""

    def __init__(self, gdi32, handles):
        self._gdi32 = gdi32
        self.handles = handles


def open_gpu_adapters():
    """Open every graphics adapter, or None when that is impossible (not
    Windows, Windows older than 10...)."""
    if not IS_WINDOWS:
        return None
    try:
        gdi32 = ctypes.windll.gdi32
        enum = _EnumAdapters2()
        # A first call gives the count, the second one fills the array.
        if gdi32.D3DKMTEnumAdapters2(ctypes.byref(enum)) != 0 or not enum.NumAdapters:
            return None
        array = (_AdapterInfo * enum.NumAdapters)()
        enum.pAdapters = array
        if gdi32.D3DKMTEnumAdapters2(ctypes.byref(enum)) != 0:
            return None
        handles = [array[index].hAdapter for index in range(enum.NumAdapters)]
        return GpuAdapters(gdi32, handles)
    except (AttributeError, OSError, ValueError):
        return None


def read_gpu_temperature(adapters):
    """Temperature of the hottest adapter in °C, None when no adapter
    reports one (integrated chips usually do not)."""
    if adapters is None:
        return None
    hottest = None
    for handle in adapters.handles:
        try:
            data = _AdapterPerfData()
            query = _QueryAdapterInfo(handle, _KMTQAITYPE_ADAPTERPERFDATA,
                                      ctypes.cast(ctypes.byref(data),
                                                  ctypes.c_void_p),
                                      ctypes.sizeof(data))
            if adapters._gdi32.D3DKMTQueryAdapterInfo(ctypes.byref(query)) != 0:
                continue
        except (AttributeError, OSError, ValueError):
            continue
        if data.Temperature:
            celsius = data.Temperature / 10.0
            hottest = celsius if hottest is None else max(hottest, celsius)
    return hottest


# --------------------------------------------------------------------------
# Notification area icon
# --------------------------------------------------------------------------

def icon_path():
    """The .ico of the application, next to the sources or, once packaged,
    in the folder PyInstaller unpacks its data to."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    return os.path.join(base, "monitor_widget", "icon.ico")


def has_tray():
    """True when an icon can be put in the notification area."""
    return IS_WINDOWS


class TrayIcon:
    """Icon of the notification area. A left click calls `on_click`, a right
    click opens a menu built by `menu()` at that moment, as a list of
    (label, callback), None standing for a separator.

    Its hidden window is served by the Tk event loop, which dispatches every
    message of the thread, so the callbacks run in the UI thread. Outside
    Windows every method does nothing.
    """

    _WM_APP_TRAY = 0x8001          # WM_APP + 1
    _WM_LBUTTONUP = 0x0202
    _WM_RBUTTONUP = 0x0205
    _WM_NULL = 0x0000
    _NIM_ADD, _NIM_DELETE = 0, 2
    _NIF_MESSAGE, _NIF_ICON, _NIF_TIP = 1, 2, 4
    _MF_SEPARATOR = 0x0800
    _TPM_RIGHTBUTTON, _TPM_RETURNCMD = 0x0002, 0x0100
    _IMAGE_ICON, _LR_LOADFROMFILE = 1, 0x0010
    _IDI_APPLICATION = 32512
    _CLASS_NAME = "MonitorWidgetTray"

    def __init__(self, tooltip, on_click, menu):
        self._tooltip = tooltip
        self._on_click = on_click
        self._menu = menu
        self._window = None
        self._shown = False
        self._procedure = None     # kept alive: Windows calls it back

    def show(self):
        if not IS_WINDOWS or self._shown:
            return
        try:
            if self._window is None:
                self._create_window()
            self._shown = self._notify(self._NIM_ADD)
        except (AttributeError, OSError, ValueError):
            self._shown = False

    def hide(self):
        if not IS_WINDOWS or not self._shown:
            return
        try:
            self._notify(self._NIM_DELETE)
        except (AttributeError, OSError, ValueError):
            pass
        self._shown = False

    def _create_window(self):
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = wintypes.LPARAM
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        # Handles are pointer sized: left untyped, ctypes would cut them.
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                       ctypes.c_size_t, wintypes.LPCWSTR]
        user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT,
                                          ctypes.c_int, ctypes.c_int,
                                          ctypes.c_int, wintypes.HWND,
                                          ctypes.c_void_p]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
        kernel32 = ctypes.windll.kernel32
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        procedure_type = ctypes.WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND,
                                            wintypes.UINT, wintypes.WPARAM,
                                            wintypes.LPARAM)

        class WindowClass(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT),
                        ("lpfnWndProc", procedure_type),
                        ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE),
                        ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE),
                        ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR),
                        ("lpszClassName", wintypes.LPCWSTR)]

        # Sent to every top level window when Explorer restarts: the icon
        # has to be added again.
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._procedure = procedure_type(self._handle)
        instance = kernel32.GetModuleHandleW(None)
        window_class = WindowClass(lpfnWndProc=self._procedure,
                                   hInstance=instance,
                                   lpszClassName=self._CLASS_NAME)
        # Fails harmlessly when the class already exists.
        user32.RegisterClassW(ctypes.byref(window_class))
        # A plain hidden window rather than a message-only one: those never
        # hear about Explorer restarting.
        self._window = user32.CreateWindowExW(0, self._CLASS_NAME,
                                              self._CLASS_NAME, 0, 0, 0, 0, 0,
                                              None, None, instance, None)
        self._icon = self._load_icon()

    def _load_icon(self):
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                      wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                      wintypes.UINT]
        size = user32.GetSystemMetrics(49)       # SM_CXSMICON
        icon = user32.LoadImageW(None, icon_path(), self._IMAGE_ICON,
                                 size, size, self._LR_LOADFROMFILE)
        if not icon:
            user32.LoadIconW.restype = wintypes.HICON
            user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
            icon = user32.LoadIconW(None, ctypes.c_void_p(self._IDI_APPLICATION))
        return icon

    def _notify(self, action):
        from ctypes import wintypes

        class NotifyIconData(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("hWnd", wintypes.HWND),
                        ("uID", wintypes.UINT),
                        ("uFlags", wintypes.UINT),
                        ("uCallbackMessage", wintypes.UINT),
                        ("hIcon", wintypes.HICON),
                        ("szTip", wintypes.WCHAR * 128),
                        ("dwState", wintypes.DWORD),
                        ("dwStateMask", wintypes.DWORD),
                        ("szInfo", wintypes.WCHAR * 256),
                        ("uVersion", wintypes.UINT),
                        ("szInfoTitle", wintypes.WCHAR * 64),
                        ("dwInfoFlags", wintypes.DWORD),
                        ("guidItem", ctypes.c_ubyte * 16),
                        ("hBalloonIcon", wintypes.HICON)]

        data = NotifyIconData()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self._window
        data.uID = 1
        if action == self._NIM_ADD:
            data.uFlags = self._NIF_MESSAGE | self._NIF_ICON | self._NIF_TIP
            data.uCallbackMessage = self._WM_APP_TRAY
            data.hIcon = self._icon
            data.szTip = self._tooltip[:127]
        return bool(ctypes.windll.shell32.Shell_NotifyIconW(action,
                                                            ctypes.byref(data)))

    def _handle(self, window, message, wparam, lparam):
        user32 = ctypes.windll.user32
        try:
            if message == self._WM_APP_TRAY:
                event = lparam & 0xFFFF
                if event == self._WM_LBUTTONUP:
                    self._on_click()
                elif event == self._WM_RBUTTONUP:
                    self._popup()
                return 0
            if message == self._taskbar_created and self._shown:
                self._notify(self._NIM_ADD)
        except Exception:
            # An exception must never cross back into Windows.
            pass
        return user32.DefWindowProcW(window, message, wparam, lparam)

    def _popup(self):
        user32 = ctypes.windll.user32
        entries = self._menu()
        menu = user32.CreatePopupMenu()
        try:
            for number, entry in enumerate(entries, 1):
                if entry is None:
                    user32.AppendMenuW(menu, self._MF_SEPARATOR, 0, None)
                else:
                    user32.AppendMenuW(menu, 0, number, entry[0])
            point = _POINT()
            user32.GetCursorPos(ctypes.byref(point))
            # Without it the menu stays open when clicking elsewhere.
            user32.SetForegroundWindow(self._window)
            chosen = user32.TrackPopupMenu(
                menu, self._TPM_RIGHTBUTTON | self._TPM_RETURNCMD,
                point.x, point.y, 0, self._window, None)
            user32.PostMessageW(self._window, self._WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)
        if 0 < chosen <= len(entries) and entries[chosen - 1] is not None:
            entries[chosen - 1][1]()


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
