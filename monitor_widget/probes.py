# -*- coding: utf-8 -*-
"""Data sources the widget can display.

To add a metric (network throughput, temperature, free disk space...):
write a class inheriting from `Probe`, give it a `key` and a `label`,
implement `read()`, then decorate it with `@register`. The context menu of
the widget picks it up automatically.
"""

import psutil

# Available probes, in declaration order.
PROBES = {}


def register(cls):
    """Decorator adding a probe to the registry."""
    PROBES[cls.key] = cls
    return cls


class Probe:
    """A displayable metric: one bounded number, refreshed every second."""

    key = "abstract"
    label = "Metric"
    unit = "%"
    minimum = 0.0
    maximum = 100.0

    def start(self):
        """Called once before the first read (optional priming)."""

    def read(self):
        """Return the current value. Must never block."""
        raise NotImplementedError

    def format(self, value):
        """Text shown in large type inside the widget."""
        return "{:.0f}{}".format(value, self.unit)

    def ratio(self, value):
        """Position of the value between 0 and 1, for the graph and color."""
        span = self.maximum - self.minimum
        if span <= 0:
            return 0.0
        return max(0.0, min((value - self.minimum) / span, 1.0))


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


@register
class MemoryProbe(Probe):
    """Used physical memory, as a percentage. Also serves as the example of
    how a new metric is plugged in."""

    key = "ram"
    label = "RAM"

    def read(self):
        return psutil.virtual_memory().percent
