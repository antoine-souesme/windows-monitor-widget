# -*- coding: utf-8 -*-
"""Everything Windows specific: single instance, window styles, connected
displays, GPU counters, frame rates, auto start, notification area icon and
the real place of files inside a Store package.

Every function stays callable outside Windows (doing nothing useful, but not
failing), so the rest of the program can be read and tested elsewhere.
"""

import atexit
import ctypes
import os
import sys
import threading
import uuid
from collections import deque

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
# Frame rate: frames shown by the games (event tracing) and by the desktop
# --------------------------------------------------------------------------

# Fixed width types, so the layouts below can be checked on any system.
_u8, _u16, _u32, _u64, _i64 = (ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32,
                               ctypes.c_uint64, ctypes.c_int64)


class _Guid(ctypes.Structure):
    _fields_ = [("Data1", _u32), ("Data2", _u16), ("Data3", _u16),
                ("Data4", _u8 * 8)]


def _guid(text):
    return _Guid.from_buffer_copy(uuid.UUID(text).bytes_le)


class _WnodeHeader(ctypes.Structure):
    _fields_ = [("BufferSize", _u32), ("ProviderId", _u32),
                ("HistoricalContext", _u64), ("TimeStamp", _i64),
                ("Guid", _Guid), ("ClientContext", _u32), ("Flags", _u32)]


class _TraceProperties(ctypes.Structure):
    """EVENT_TRACE_PROPERTIES."""
    _fields_ = [("Wnode", _WnodeHeader), ("BufferSize", _u32),
                ("MinimumBuffers", _u32), ("MaximumBuffers", _u32),
                ("MaximumFileSize", _u32), ("LogFileMode", _u32),
                ("FlushTimer", _u32), ("EnableFlags", _u32),
                ("AgeLimit", ctypes.c_int32), ("NumberOfBuffers", _u32),
                ("FreeBuffers", _u32), ("EventsLost", _u32),
                ("BuffersWritten", _u32), ("LogBuffersLost", _u32),
                ("RealTimeBuffersLost", _u32), ("LoggerThreadId", ctypes.c_void_p),
                ("LogFileNameOffset", _u32), ("LoggerNameOffset", _u32)]


class _TracePropertiesBuffer(ctypes.Structure):
    """The properties followed by the room Windows writes the session name to."""
    _fields_ = [("properties", _TraceProperties), ("name", _u16 * 256)]


class _EventTraceHeader(ctypes.Structure):
    _fields_ = [("Size", _u16), ("FieldTypeFlags", _u16), ("Version", _u32),
                ("ThreadId", _u32), ("ProcessId", _u32), ("TimeStamp", _i64),
                ("Guid", _Guid), ("ProcessorTime", _u64)]


class _EventTrace(ctypes.Structure):
    _fields_ = [("Header", _EventTraceHeader), ("InstanceId", _u32),
                ("ParentInstanceId", _u32), ("ParentGuid", _Guid),
                ("MofData", ctypes.c_void_p), ("MofLength", _u32),
                ("ClientContext", _u32)]


class _SystemTime(ctypes.Structure):
    _fields_ = [(name, _u16) for name in ("Year", "Month", "DayOfWeek", "Day",
                                          "Hour", "Minute", "Second",
                                          "Milliseconds")]


class _TimeZone(ctypes.Structure):
    _fields_ = [("Bias", ctypes.c_int32), ("StandardName", _u16 * 32),
                ("StandardDate", _SystemTime), ("StandardBias", ctypes.c_int32),
                ("DaylightName", _u16 * 32), ("DaylightDate", _SystemTime),
                ("DaylightBias", ctypes.c_int32)]


class _LogfileHeader(ctypes.Structure):
    """TRACE_LOGFILE_HEADER."""
    _fields_ = [("BufferSize", _u32), ("Version", _u32),
                ("ProviderVersion", _u32), ("NumberOfProcessors", _u32),
                ("EndTime", _i64), ("TimerResolution", _u32),
                ("MaximumFileSize", _u32), ("LogFileMode", _u32),
                ("BuffersWritten", _u32), ("LogInstanceGuid", _Guid),
                ("LoggerName", ctypes.c_void_p), ("LogFileName", ctypes.c_void_p),
                ("TimeZone", _TimeZone), ("BootTime", _i64), ("PerfFreq", _i64),
                ("StartTime", _i64), ("ReservedFlags", _u32),
                ("BuffersLost", _u32)]


class _EventDescriptor(ctypes.Structure):
    _fields_ = [("Id", _u16), ("Version", _u8), ("Channel", _u8),
                ("Level", _u8), ("Opcode", _u8), ("Task", _u16),
                ("Keyword", _u64)]


class _EventHeader(ctypes.Structure):
    _fields_ = [("Size", _u16), ("HeaderType", _u16), ("Flags", _u16),
                ("EventProperty", _u16), ("ThreadId", _u32),
                ("ProcessId", _u32), ("TimeStamp", _i64),
                ("ProviderId", _Guid), ("EventDescriptor", _EventDescriptor),
                ("ProcessorTime", _u64), ("ActivityId", _Guid)]


class _EventRecord(ctypes.Structure):
    _fields_ = [("EventHeader", _EventHeader), ("BufferContext", _u32),
                ("ExtendedDataCount", _u16), ("UserDataLength", _u16),
                ("ExtendedData", ctypes.c_void_p), ("UserData", ctypes.c_void_p),
                ("UserContext", ctypes.c_void_p)]


_EventRecordCallback = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    None, ctypes.POINTER(_EventRecord))


class _TraceLogfile(ctypes.Structure):
    """EVENT_TRACE_LOGFILEW."""
    _fields_ = [("LogFileName", ctypes.c_wchar_p), ("LoggerName", ctypes.c_wchar_p),
                ("CurrentTime", _i64), ("BuffersRead", _u32),
                ("ProcessTraceMode", _u32), ("CurrentEvent", _EventTrace),
                ("LogfileHeader", _LogfileHeader),
                ("BufferCallback", ctypes.c_void_p), ("BufferSize", _u32),
                ("Filled", _u32), ("EventsLost", _u32),
                ("EventRecordCallback", _EventRecordCallback),
                ("IsKernelTrace", _u32), ("Context", ctypes.c_void_p)]


_TRACE_NAME = "MonitorWidgetFrames"
# Providers writing an event each time a program shows a frame: DXGI covers
# Direct3D 10 to 12 (and the Vulkan or OpenGL games drawn through it), D3D9
# the older games.
_DXGI = "{CA11C036-0102-4A2D-A6AD-F03CFED5D3C9}"
_D3D9 = "{783ACA0A-790E-4D7F-8451-AA850511C6B9}"
# (first part of the provider id, event id) of each "frame shown" event.
_PRESENT_EVENTS = {(0xCA11C036, 42), (0xCA11C036, 55), (0x783ACA0A, 1)}
_WNODE_FLAG_TRACED_GUID = 0x00020000
_EVENT_TRACE_REAL_TIME_MODE = 0x00000100
_EVENT_TRACE_CONTROL_STOP = 1
_ENABLE_PROVIDER = 1
_TRACE_LEVEL_INFORMATION = 4
_PROCESS_TRACE_MODE_REAL_TIME = 0x00000100
_PROCESS_TRACE_MODE_RAW_TIMESTAMP = 0x00001000
_PROCESS_TRACE_MODE_EVENT_RECORD = 0x10000000
_ERROR_ACCESS_DENIED = 5
_INVALID_TRACE = (1 << 8 * ctypes.sizeof(ctypes.c_void_p)) - 1
# Built in group allowed to trace events without being administrator
# ("Performance Log Users"), named by its id so any language works.
_PERFORMANCE_LOG_USERS = "S-1-5-32-559"

_trace = None
_trace_denied = False


def performance_counter():
    """Current time in ticks of the performance counter, the clock of the
    frame times. 0 outside Windows."""
    if not IS_WINDOWS:
        return 0
    ticks = _i64()
    ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(ticks))
    return ticks.value


def _trace_functions():
    """advapi32 with the prototypes of the trace functions, kept apart from
    ctypes.windll so the other callers are not affected."""
    advapi32 = ctypes.WinDLL("advapi32")
    session = _u64
    properties = ctypes.POINTER(_TraceProperties)
    advapi32.StartTraceW.argtypes = [ctypes.POINTER(session), ctypes.c_wchar_p,
                                     properties]
    advapi32.StartTraceW.restype = _u32
    advapi32.ControlTraceW.argtypes = [session, ctypes.c_wchar_p, properties, _u32]
    advapi32.ControlTraceW.restype = _u32
    advapi32.EnableTraceEx2.argtypes = [session, ctypes.POINTER(_Guid), _u32,
                                        _u8, _u64, _u64, _u32, ctypes.c_void_p]
    advapi32.EnableTraceEx2.restype = _u32
    advapi32.OpenTraceW.argtypes = [ctypes.POINTER(_TraceLogfile)]
    advapi32.OpenTraceW.restype = session
    advapi32.ProcessTrace.argtypes = [ctypes.POINTER(session), _u32,
                                      ctypes.c_void_p, ctypes.c_void_p]
    advapi32.ProcessTrace.restype = _u32
    advapi32.CloseTrace.argtypes = [session]
    advapi32.CloseTrace.restype = _u32
    return advapi32


def _trace_properties():
    """Fresh properties of a real time session, flushed every second."""
    buffer = _TracePropertiesBuffer()
    properties = buffer.properties
    properties.Wnode.BufferSize = ctypes.sizeof(buffer)
    properties.Wnode.Flags = _WNODE_FLAG_TRACED_GUID
    properties.Wnode.ClientContext = 1          # performance counter clock
    properties.LogFileMode = _EVENT_TRACE_REAL_TIME_MODE
    properties.FlushTimer = 1
    properties.LoggerNameOffset = ctypes.sizeof(_TraceProperties)
    return buffer


def _control(buffer):
    """Pointer to the properties at the head of a buffer."""
    return ctypes.cast(ctypes.byref(buffer), ctypes.POINTER(_TraceProperties))


class PresentTrace:
    """Real time trace session noting when each process shows a frame. Its
    events are read on a thread of their own, which blocks while it waits."""

    KEPT = 1000          # latest frame times kept for each process
    FORGOTTEN = 5        # seconds without a frame before a process is dropped

    def __init__(self, advapi32):
        self._advapi32 = advapi32
        self._lock = threading.Lock()
        self._stamps = {}        # process id -> deque of frame times
        self._callback = _EventRecordCallback(self._on_event)
        frequency = _i64()
        ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency))
        self.frequency = frequency.value
        threading.Thread(target=self._consume, name="Frame trace",
                         daemon=True).start()

    def _on_event(self, record):
        header = record.contents.EventHeader
        if (header.ProviderId.Data1, header.EventDescriptor.Id) not in _PRESENT_EVENTS:
            return
        with self._lock:
            stamps = self._stamps.get(header.ProcessId)
            if stamps is None:
                stamps = self._stamps[header.ProcessId] = deque(maxlen=self.KEPT)
            stamps.append(header.TimeStamp)

    def _consume(self):
        """Deliver the events until the session is stopped. A failure lands
        in the log through the thread error hook."""
        logfile = _TraceLogfile()
        logfile.LoggerName = _TRACE_NAME
        # Raw times: the performance counter, not converted to dates.
        logfile.ProcessTraceMode = (_PROCESS_TRACE_MODE_REAL_TIME
                                    | _PROCESS_TRACE_MODE_EVENT_RECORD
                                    | _PROCESS_TRACE_MODE_RAW_TIMESTAMP)
        logfile.EventRecordCallback = self._callback
        handle = _u64(self._advapi32.OpenTraceW(ctypes.byref(logfile)))
        if handle.value == _INVALID_TRACE:
            raise OSError("OpenTrace failed: {}".format(ctypes.GetLastError()))
        try:
            self._advapi32.ProcessTrace(ctypes.byref(handle), 1, None, None)
        finally:
            self._advapi32.CloseTrace(handle)

    def stamps(self, process):
        """Times of the latest frames of a process, oldest first."""
        limit = performance_counter() - self.FORGOTTEN * self.frequency
        with self._lock:
            for key in [key for key, stamps in self._stamps.items()
                        if not stamps or stamps[-1] < limit]:
                del self._stamps[key]
            return list(self._stamps.get(process, ()))


def start_present_trace():
    """Start noting the frames every process shows, or None when Windows
    refuses (see present_trace_denied) or cannot (not Windows...). One
    session for the whole program."""
    global _trace, _trace_denied
    if _trace is not None or not IS_WINDOWS:
        return _trace
    try:
        advapi32 = _trace_functions()
        session = _u64()
        buffer = _trace_properties()
        status = advapi32.StartTraceW(ctypes.byref(session), _TRACE_NAME,
                                      _control(buffer))
        if status == _ERROR_ALREADY_EXISTS:
            # Left behind by a run that ended without stopping it.
            advapi32.ControlTraceW(0, _TRACE_NAME,
                                   _control(_trace_properties()),
                                   _EVENT_TRACE_CONTROL_STOP)
            buffer = _trace_properties()
            status = advapi32.StartTraceW(ctypes.byref(session), _TRACE_NAME,
                                          _control(buffer))
        _trace_denied = status == _ERROR_ACCESS_DENIED
        if status != 0:
            return None
        for provider in (_DXGI, _D3D9):
            advapi32.EnableTraceEx2(session, ctypes.byref(_guid(provider)),
                                    _ENABLE_PROVIDER, _TRACE_LEVEL_INFORMATION,
                                    0, 0, 0, None)
        _trace = PresentTrace(advapi32)
        # A session outlives the program that started it.
        atexit.register(stop_present_trace)
        return _trace
    except (AttributeError, OSError, ValueError):
        return None


def stop_present_trace():
    """Stop the session started by start_present_trace, if any."""
    global _trace
    if _trace is None:
        return
    try:
        _trace._advapi32.ControlTraceW(0, _TRACE_NAME,
                                       _control(_trace_properties()),
                                       _EVENT_TRACE_CONTROL_STOP)
    except (AttributeError, OSError, ValueError):
        pass
    _trace = None


def present_trace_denied():
    """True when Windows refused the last attempt to note the frames: the
    account is neither administrator nor in the Performance Log Users group."""
    return _trace_denied


def grant_present_trace():
    """Add the current account to the Performance Log Users group, through
    the administrator prompt of Windows. It takes effect at the next logon.
    True when the prompt could be shown."""
    if not IS_WINDOWS:
        return False
    domain, user = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
    if not user:
        return False
    # The command runs as the administrator who answers the prompt, who may
    # not be the user: the account is named here, in a quoted string.
    account = "{}\\{}".format(domain, user) if domain else user
    command = "Add-LocalGroupMember -SID {} -Member '{}'".format(
        _PERFORMANCE_LOG_USERS, account.replace("'", "''"))
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            "-NoProfile -WindowStyle Hidden -Command \"{}\"".format(command),
            None, 0)
    except (AttributeError, OSError):
        return False
    # Above 32 means started; a refused prompt gives an error code.
    return result > 32


class _UnsignedRatio(ctypes.Structure):
    _fields_ = [("Numerator", _u32), ("Denominator", _u32)]


class _DwmTimingInfo(ctypes.Structure):
    """DWM_TIMING_INFO, packed on single bytes like in dwmapi.h."""
    _pack_ = 1
    _fields_ = ([("cbSize", _u32), ("rateRefresh", _UnsignedRatio),
                 ("qpcRefreshPeriod", _u64), ("rateCompose", _UnsignedRatio),
                 ("qpcVBlank", _u64), ("cRefresh", _u64), ("cDXRefresh", _u32),
                 ("qpcCompose", _u64), ("cFrame", _u64), ("cDXPresent", _u32),
                 ("cRefreshFrame", _u64), ("cFrameSubmitted", _u64),
                 ("cDXPresentSubmitted", _u32), ("cFrameConfirmed", _u64),
                 ("cDXPresentConfirmed", _u32), ("cRefreshConfirmed", _u64),
                 ("cDXRefreshConfirmed", _u32), ("cFramesLate", _u64),
                 ("cFramesOutstanding", _u32)]
                + [(name, _u64) for name in (
                    "cFrameDisplayed", "qpcFrameDisplayed",
                    "cRefreshFrameDisplayed", "cFrameComplete",
                    "qpcFrameComplete", "cFramePending", "qpcFramePending",
                    "cFramesDisplayed", "cFramesComplete", "cFramesPending",
                    "cFramesAvailable", "cFramesDropped", "cFramesMissed",
                    "cRefreshNextDisplayed", "cRefreshNextPresented",
                    "cRefreshesDisplayed", "cRefreshesPresented",
                    "cRefreshStarted", "cPixelsReceived", "cPixelsDrawn",
                    "cBuffersEmpty")])


def read_desktop_frames():
    """Frames the desktop has composed so far, None when Windows does not
    say (or outside Windows)."""
    if not IS_WINDOWS:
        return None
    try:
        info = _DwmTimingInfo()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.dwmapi.DwmGetCompositionTimingInfo(
                None, ctypes.byref(info)) != 0:
            return None
        return info.cFrame
    except (AttributeError, OSError):
        return None


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int32), ("top", ctypes.c_int32),
                ("right", ctypes.c_int32), ("bottom", ctypes.c_int32)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", _u32), ("rcMonitor", _Rect), ("rcWork", _Rect),
                ("dwFlags", _u32)]


def fullscreen_process():
    """Id of the process owning the foreground window when that window
    covers its whole display (a game in full screen), None otherwise."""
    if not IS_WINDOWS:
        return None
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetShellWindow.restype = ctypes.c_void_p
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
        user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, _u32]
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(_MonitorInfo)]
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                                    ctypes.POINTER(_u32)]
        window = user32.GetForegroundWindow()
        # The desktop itself covers the screen too.
        if not window or window == user32.GetShellWindow():
            return None
        rect = _Rect()
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        monitor = user32.MonitorFromWindow(window, _MONITOR_DEFAULTTONULL)
        if (not monitor or not user32.GetWindowRect(window, ctypes.byref(rect))
                or not user32.GetMonitorInfoW(monitor, ctypes.byref(info))):
            return None
        screen = info.rcMonitor
        if (rect.left > screen.left or rect.top > screen.top
                or rect.right < screen.right or rect.bottom < screen.bottom):
            return None
        process = _u32()
        user32.GetWindowThreadProcessId(window, ctypes.byref(process))
        return process.value or None
    except (AttributeError, OSError, ValueError):
        return None


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


def _package_family_name():
    """Family name of the running package, None outside a package."""
    if not IS_WINDOWS:
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        length = ctypes.c_uint32(0)
        kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), None)
        if not length.value:
            return None
        buffer = ctypes.create_unicode_buffer(length.value)
        if kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), buffer) != 0:
            return None
        return buffer.value
    except (AttributeError, OSError):
        return None


def real_path(path):
    """Where a file of %APPDATA% really is on disk.

    Inside a package Windows quietly redirects what the widget writes to
    %APPDATA% into the package's own folder. The widget does not notice, but
    the Explorer, which runs outside the package, only sees the real place.
    """
    family = _package_family_name()
    appdata = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    if not family or not appdata or not local:
        return path
    try:
        relative = os.path.relpath(path, appdata)
    except ValueError:
        return path
    if relative.startswith(".."):
        return path
    redirected = os.path.join(local, "Packages", family, "LocalCache",
                              "Roaming", relative)
    return redirected if os.path.exists(redirected) else path


def show_file(path):
    """Open the folder of `path` in the file manager, the file selected when
    possible. Return False when nothing could be opened."""
    import subprocess
    path = real_path(path)
    folder = os.path.dirname(path)
    try:
        if IS_WINDOWS:
            if os.path.exists(path):
                subprocess.Popen(["explorer", "/select,", path])
            else:
                os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if os.path.exists(path)
                             else ["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
        return True
    except (AttributeError, OSError):
        return False
