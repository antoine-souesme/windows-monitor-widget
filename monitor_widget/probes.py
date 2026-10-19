# -*- coding: utf-8 -*-
"""Data sources the widget can display.

To add a metric (temperature, free disk space...): write a class inheriting
from `Probe`, give it a `key` and a `label`, implement `read()`, then decorate
it with `@register`. The context menu of the widget picks it up automatically.

A metric can also offer choices (`options`): they show up under "Options des
métriques", are stored in the configuration file and handed back to the probe
through `configure()`. A metric can finally draw several values side by side
inside its block by returning a tuple from `read()`.

`slots()` names every value a metric can measure, whatever its options: the
custom grid offers each of them separately. A metric whose options hide some
of its values forces them back in custom mode through `custom_values`, so its
columns always match its slots there.
"""

import time
from collections import deque

import psutil

from . import system

# Available probes, in declaration order.
PROBES = {}

# Seconds of history a self scaling metric looks at, same span as the graph.
PEAK_POINTS = 60


def register(cls):
    """Decorator adding a probe to the registry."""
    PROBES[cls.key] = cls
    return cls


class Option:
    """A choice offered for one metric in the context menu."""

    def __init__(self, key, default, choices):
        self.key = key            # configuration key holding the answer
        self.default = default    # value used on first launch
        self.choices = choices    # list of (value, French label)

    def values(self):
        return [value for value, _label in self.choices]


def option_defaults():
    """Default value of every option declared by every metric."""
    defaults = {}
    for cls in PROBES.values():
        for option in cls.options:
            defaults[option.key] = option.default
    return defaults


def options():
    """All the metrics offering choices, in declaration order."""
    return [cls for cls in PROBES.values() if cls.options]


def configured_values(values, custom):
    """Configuration handed to the metrics: in custom mode every metric's
    `custom_values` override the stored choices. `values` is left as is."""
    configured = dict(values)
    if custom:
        for cls in PROBES.values():
            configured.update(cls.custom_values)
    return configured


def custom_hidden_options():
    """Option keys that mean nothing in custom mode, as it forces them."""
    hidden = set()
    for cls in PROBES.values():
        hidden.update(cls.custom_values)
    return hidden


def _scale(value):
    """Turn a size in bytes into a readable number and its unit."""
    units = ["o", "Ko", "Mo", "Go", "To"]
    index = 0
    value = float(value)
    while value >= 1024.0 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    return value, units[index]


def _number(value):
    """French looking number: a comma, and decimals only when they matter."""
    if value >= 100 or abs(value - round(value)) < 0.05:
        return "{:.0f}".format(value)
    return "{:.1f}".format(value).replace(".", ",")


class Probe:
    """A displayable metric: one bounded number, refreshed every second."""

    key = "abstract"
    label = "Metric"
    unit = "%"
    minimum = 0.0
    maximum = 100.0
    options = ()
    # Option values forced in custom mode, where each cell picks its value.
    custom_values = {}

    @classmethod
    def slots(cls):
        """French name of every value the metric can measure, whatever its
        options, in column order."""
        return [cls.label]

    def start(self):
        """Called once before the first read (optional priming)."""

    def configure(self, values):
        """Receive the configuration, once at creation and at every change."""

    def columns(self):
        """How many values the block draws side by side."""
        return 1

    def read(self):
        """Return the current value, or one value per column. Never blocks."""
        raise NotImplementedError

    def format(self, value):
        """Text shown in large type for a single value."""
        return "{:.0f}{}".format(value, self.unit)

    def texts(self, values):
        """Text shown in large type, one per column."""
        return [self.format(value) for value in values]

    def captions(self):
        """Name written before each value in compact mode, where every value
        of a metric gets lines of its own."""
        return [self.label] * self.columns()

    def prefixes(self):
        """Mark drawn before each number, at a size of its own, or None."""
        return [None] * self.columns()

    def template(self):
        """Widest text a column can hold. The drawing picks the font size on
        it rather than on the current value, so the number never resizes."""
        return self.format(self.maximum)

    def ratio(self, value, column=0):
        """Position of the value between 0 and 1, for the graph and color."""
        span = self.maximum - self.minimum
        if span <= 0:
            return 0.0
        return max(0.0, min((value - self.minimum) / span, 1.0))

    def tint(self, column=0):
        """Fixed color of a column, or None to use the green to red scale."""
        return None


@register
class CpuProbe(Probe):
    """Overall processor load, as a percentage."""

    key = "cpu"
    label = "CPU"

    def start(self):
        # First call: it only sets the reference point and returns 0.
        psutil.cpu_percent(interval=None)

    def read(self):
        return psutil.cpu_percent(interval=None)


def busiest_engine(samples):
    """Load of the busiest GPU engine, as the Task Manager shows it: the
    processes sharing one engine add up, then the busiest engine wins."""
    engines = {}
    for name, value in samples:
        # "pid_1234_luid_..._eng_0_engtype_3D": the engine is what follows
        # the process id.
        engine = name[name.find("luid_"):] if "luid_" in name else name
        engines[engine] = engines.get(engine, 0.0) + max(0.0, value)
    return min(max(engines.values(), default=0.0), 100.0)


@register
class GpuProbe(Probe):
    """Load of the graphics card, whatever its brand. Reads 0 when Windows
    gives no GPU counters (or outside Windows)."""

    key = "gpu"
    label = "GPU"

    def __init__(self):
        self._query = None

    def start(self):
        self._query = system.open_gpu_query()

    def read(self):
        return busiest_engine(system.read_gpu_engines(self._query))


@register
class MemoryProbe(Probe):
    """Used physical memory. Also serves as the example of how a new metric,
    with its own options, is plugged in."""

    key = "ram"
    label = "RAM"
    options = (Option("ram_display", "percent",
                      [("percent", "Pourcentage"),
                       ("both", "Pourcentage et valeur"),
                       ("value", "Valeur")]),)

    def __init__(self):
        self._display = "percent"
        self._used = 0
        self._total = 0

    def configure(self, values):
        self._display = values.get("ram_display", "percent")

    def read(self):
        memory = psutil.virtual_memory()
        self._used = memory.total - memory.available
        self._total = memory.total
        return memory.percent

    def format(self, value):
        percent = "{:.0f}%".format(value)
        if self._display == "percent" or not self._total:
            return percent
        # Both numbers share the unit of the total, so they stay comparable.
        total, unit = _scale(self._total)
        used = self._used / (self._total / total) if total else 0.0
        size = "{}/{} {}".format(_number(used), _number(total), unit)
        if self._display == "value":
            return size
        return "{} · {}".format(percent, size)

    def template(self):
        # Full percentage, and a used value as wide as it can get: below a
        # hundred it carries a decimal the total does not.
        if self._display == "percent" or not self._total:
            return "100%"
        total, unit = _scale(self._total)
        widest = "{:.0f},9".format(total) if total < 100 else _number(total)
        size = "{}/{} {}".format(widest, _number(total), unit)
        if self._display == "value":
            return size
        return "100% · {}".format(size)


@register
class NetworkProbe(Probe):
    """Network throughput, in bytes per second. It has no known maximum, so
    each graph scales itself on the strongest rate of the last minute."""

    key = "net"
    label = "Réseau"
    options = (Option("network_display", "both",
                      [("download", "Réception"),
                       ("both", "Réception et envoi"),
                       ("upload", "Envoi")]),)
    custom_values = {"network_display": "both"}
    # Enough of a rate to be worth drawing: below that the graph stays flat
    # instead of turning noise into a mountain.
    FLOOR = 64 * 1024.0
    # Purple: the green to red scale of the other metrics already owns green,
    # so each graph keeps a color of its own.
    DOWNLOAD_COLOR = "#ab47bc"
    UPLOAD_COLOR = "#42a5f5"

    def __init__(self):
        self._display = "both"
        self._counters = None
        self._time = None
        self._peaks = [deque([0.0] * PEAK_POINTS, maxlen=PEAK_POINTS),
                       deque([0.0] * PEAK_POINTS, maxlen=PEAK_POINTS)]

    @classmethod
    def slots(cls):
        return ["Réseau réception", "Réseau envoi"]

    def configure(self, values):
        self._display = values.get("network_display", "both")

    def start(self):
        self._counters = self._counts()
        self._time = time.monotonic()

    def _counts(self):
        try:
            counters = psutil.net_io_counters()
        except Exception:
            return None
        if counters is None:
            return None
        return (counters.bytes_recv, counters.bytes_sent)

    def columns(self):
        return 2 if self._display == "both" else 1

    def read(self):
        counters = self._counts()
        now = time.monotonic()
        rates = (0.0, 0.0)
        if counters is not None and self._counters is not None:
            elapsed = now - self._time if self._time is not None else 0.0
            if elapsed > 0:
                # A counter can go backwards when an interface is reset.
                rates = tuple(max(0.0, (counters[i] - self._counters[i]) / elapsed)
                              for i in range(2))
        self._counters = counters
        self._time = now
        selected = self._selected(rates)
        for index, value in enumerate(selected):
            self._peaks[index].append(value)
        return selected

    def _selected(self, rates):
        """Keep only the directions the user asked for, in reading order."""
        if self._display == "download":
            return (rates[0],)
        if self._display == "upload":
            return (rates[1],)
        return rates

    def _arrows(self):
        if self._display == "download":
            return ["↓"]
        if self._display == "upload":
            return ["↑"]
        return ["↓", "↑"]

    def texts(self, values):
        # One unit for the whole block, so the two figures can be compared,
        # but written on each of them: a number alone means nothing.
        _scaled, unit = _scale(max(list(values) + [self.FLOOR]))
        divider = 1024.0 ** ["o", "Ko", "Mo", "Go", "To"].index(unit)
        return ["{} {}/s".format(_number(value / divider), unit)
                for value in values]

    def prefixes(self):
        return self._arrows()

    def captions(self):
        names = {"↓": "Réception", "↑": "Envoi"}
        return ["{} {}".format(arrow, names[arrow]) for arrow in self._arrows()]

    def template(self):
        # Widest rate expected on a home line; a faster one simply gets a
        # shorter number ("123 Mo/s"), so the size still holds.
        return "99,9 Mo/s"

    def ratio(self, value, column=0):
        peak = max(list(self._peaks[column]) + [self.FLOOR])
        return max(0.0, min(value / peak, 1.0))

    def tint(self, column=0):
        if self._display == "upload":
            return self.UPLOAD_COLOR
        return self.DOWNLOAD_COLOR if column == 0 else self.UPLOAD_COLOR
