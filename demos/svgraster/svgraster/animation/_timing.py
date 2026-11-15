"""SMIL timing: clock values, begin/end lists, syncbases, repeats and the active interval at a time."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

INDEFINITE = math.inf
UNITS = {"h": 3600.0, "min": 60.0, "s": 1.0, "ms": 0.001}
_CLOCK_RE = re.compile(r"^\s*(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\s*$")
_TIMECOUNT_RE = re.compile(r"^\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*(h|min|s|ms)?\s*$")
_SYNC_RE = re.compile(r"^\s*([A-Za-z_][\w.\-]*?)\.(begin|end)\s*(?:([+-])\s*(.+))?$")
_EVENT_RE = re.compile(r"^\s*(?:[A-Za-z_][\w\-]*\.)?(click|mouse\w+|focus\w*|activate|repeat\(\d+\)|accessKey\(.*\)|"
                       r"\w+Event|load|DOM\w+)", re.IGNORECASE)
MAX_SYNC_DEPTH = 16


class TimingError(ValueError):
    """Raised for clock values that cannot be parsed."""


def parse_clock(text: str | None) -> float | None:
    """Seconds for a SMIL clock value (``2s``, ``150ms``, ``1:30``, ``00:01:02.5``); ``None`` if invalid."""
    if text is None:
        return None
    text = text.strip()
    if text == "indefinite":
        return INDEFINITE
    match = _CLOCK_RE.match(text)
    if match:
        hours, minutes, seconds = match.groups()
        return int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)
    match = _TIMECOUNT_RE.match(text)
    if match:
        return float(match.group(1)) * UNITS[match.group(2) or "s"]
    return None


@dataclass
class Timing:
    """The parsed timing attributes of one animation element."""

    begins: list
    ends: list
    dur: float | None
    repeat_count: float | None
    repeat_dur: float | None
    freeze: bool

    @classmethod
    def from_node(cls, node) -> Timing:
        """Read ``begin``, ``end``, ``dur``, ``repeatCount``, ``repeatDur`` and ``fill``."""
        dur = parse_clock(node.get("dur"))
        if dur is not None and dur <= 0:
            dur = None
        rc = node.get("repeatCount")
        repeat_count = INDEFINITE if rc == "indefinite" else _positive(rc)
        rd = parse_clock(node.get("repeatDur"))
        return cls(_time_list(node.get("begin"), "0s"), _time_list(node.get("end"), None), dur, repeat_count,
                   rd if rd is None or rd > 0 else None, node.get("fill", "remove") == "freeze")

    def active_duration(self) -> float:
        """The active duration (``INDEFINITE`` when unbounded)."""
        simple = self.dur
        if simple is None:
            return self.repeat_dur if self.repeat_dur is not None else INDEFINITE
        candidates = []
        if self.repeat_count is not None:
            candidates.append(simple * self.repeat_count)
        if self.repeat_dur is not None:
            candidates.append(self.repeat_dur)
        return min(candidates) if candidates else simple


def _positive(text: str | None) -> float | None:
    try:
        value = float(text) if text is not None else None
    except ValueError:
        return None
    return value if value is not None and value > 0 else None


def _time_list(text: str | None, default: str | None) -> list:
    if text is None:
        text = default
    if text is None:
        return []
    out = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        value = parse_clock(part)
        if value is not None:
            out.append(value)
            continue
        sync = _SYNC_RE.match(part)
        if sync and not _EVENT_RE.match(part):
            ident, which, sign, offset = sync.groups()
            delta = parse_clock(offset) if offset else 0.0
            if delta is not None:
                out.append((ident, which, -delta if sign == "-" else delta))
                continue
        if part == "indefinite" or _EVENT_RE.match(part):
            out.append(INDEFINITE)
    return out


class Scheduler:
    """Resolves begin and end times (including ``id.begin``/``id.end`` syncbases) for a document."""

    def __init__(self, timings: dict[str, Timing]):
        self.timings = timings
        self._resolving: set[str] = set()

    def _resolve(self, item, depth: int) -> float:
        if not isinstance(item, tuple):
            return item
        ident, which, offset = item
        timing = self.timings.get(ident)
        if timing is None or ident in self._resolving or depth > MAX_SYNC_DEPTH:
            return INDEFINITE
        self._resolving.add(ident)
        try:
            begin = self.first_begin(timing, depth + 1)
            if which == "begin":
                return begin + offset
            return self.interval_end(timing, begin, depth + 1) + offset
        finally:
            self._resolving.discard(ident)

    def begins(self, timing: Timing, depth: int = 0) -> list[float]:
        """Resolved begin times, sorted, with unresolvable ones dropped."""
        times = [self._resolve(b, depth) for b in timing.begins]
        return sorted(t for t in times if t != INDEFINITE)

    def first_begin(self, timing: Timing, depth: int = 0) -> float:
        """The earliest resolved begin time."""
        begins = self.begins(timing, depth)
        return begins[0] if begins else INDEFINITE

    def interval_end(self, timing: Timing, begin: float, depth: int = 0) -> float:
        """The end of the interval starting at ``begin``."""
        end = begin + timing.active_duration()
        ends = sorted(self._resolve(e, depth) for e in timing.ends)
        explicit = [e for e in ends if e >= begin]
        if explicit:
            end = min(end, explicit[0])
        return end

    def interval_at(self, timing: Timing, t: float) -> tuple[float, float] | None:
        """``(begin, end)`` of the interval in effect at ``t`` (active or frozen), or ``None``."""
        found = None
        for begin in self.begins(timing):
            if begin > t:
                break
            end = self.interval_end(timing, begin)
            if end < begin:
                continue
            found = (begin, end)
            if t < end:
                return found
        if found is not None and (timing.freeze or t < found[1]):
            return found
        return None


def simple_time(timing: Timing, begin: float, end: float, t: float) -> tuple[float, int, bool] | None:
    """``(simple time, iteration, frozen)`` at ``t`` inside or after the interval ``[begin, end)``."""
    frozen = t >= end
    local = (end if frozen else t) - begin
    dur = timing.dur
    if dur is None or dur == INDEFINITE:
        return (local if dur is not None else 0.0, 0, frozen)
    iteration = int(local // dur)
    remainder = local - iteration * dur
    if frozen and remainder <= 1e-9 * max(1.0, dur) and iteration > 0:
        return (dur, iteration - 1, True)
    return (remainder, iteration, frozen)
