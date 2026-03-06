"""Windowing library for streaming consumers.

Pure Python implementations of tumbling, sliding, and session windows.
Uses event timestamps (not wall-clock), making them fully deterministic
and testable without a running broker.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """Result emitted when a window closes."""

    window_start: float
    window_end: float
    events: list[dict[str, Any]]
    key: str = ""


class TumblingWindow:
    """Fixed-size, non-overlapping time windows.

    Events are bucketed by ``event_time // window_size_seconds``.
    When a new event arrives in a later bucket, all earlier buckets are closed.
    """

    def __init__(self, window_size_seconds: float):
        self.window_size = window_size_seconds
        # key -> {bucket_id -> [events]}
        self._buckets: dict[str, dict[int, list[dict]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def add(self, event: dict[str, Any], event_time: float, key: str = "") -> list[WindowResult]:
        """Add an event and return any closed windows."""
        bucket_id = int(event_time // self.window_size)
        self._buckets[key][bucket_id].append(event)

        # Close all earlier buckets for this key
        closed = []
        for bid in sorted(self._buckets[key].keys()):
            if bid < bucket_id:
                events = self._buckets[key].pop(bid)
                closed.append(WindowResult(
                    window_start=bid * self.window_size,
                    window_end=(bid + 1) * self.window_size,
                    events=events,
                    key=key,
                ))
        return closed

    def flush(self, key: str = "") -> list[WindowResult]:
        """Force-close all open windows for a key."""
        closed = []
        if key in self._buckets:
            for bid in sorted(self._buckets[key].keys()):
                events = self._buckets[key].pop(bid)
                closed.append(WindowResult(
                    window_start=bid * self.window_size,
                    window_end=(bid + 1) * self.window_size,
                    events=events,
                    key=key,
                ))
        return closed

    def flush_all(self) -> list[WindowResult]:
        """Force-close all open windows for all keys."""
        closed = []
        for key in list(self._buckets.keys()):
            closed.extend(self.flush(key))
        return closed


class SlidingWindow:
    """Overlapping time windows with a fixed size and slide interval.

    Each event can appear in multiple windows. Windows are emitted when
    a new event's timestamp exceeds the window's end time.
    """

    def __init__(self, window_size_seconds: float, slide_seconds: float):
        self.window_size = window_size_seconds
        self.slide = slide_seconds
        # key -> [events] (sorted by time)
        self._events: dict[str, list[tuple[float, dict]]] = defaultdict(list)
        # key -> last emitted window end
        self._last_emitted: dict[str, float] = {}

    def add(self, event: dict[str, Any], event_time: float, key: str = "") -> list[WindowResult]:
        """Add an event and return any completed windows."""
        self._events[key].append((event_time, event))
        self._events[key].sort(key=lambda x: x[0])

        closed = []
        last = self._last_emitted.get(key, None)

        # Determine which window ends we've passed
        if last is None:
            # First event — no windows to close yet unless we have enough span
            first_time = self._events[key][0][0]
            # Align to slide boundary
            first_window_end = first_time + self.window_size
            last = first_window_end - self.slide  # will emit first window at first_window_end

        # Emit windows whose end <= event_time
        window_end = last + self.slide
        while window_end <= event_time:
            window_start = window_end - self.window_size
            window_events = [
                ev for t, ev in self._events[key]
                if window_start <= t < window_end
            ]
            if window_events:
                closed.append(WindowResult(
                    window_start=window_start,
                    window_end=window_end,
                    events=window_events,
                    key=key,
                ))
            self._last_emitted[key] = window_end
            window_end += self.slide

        # Evict old events outside any possible future window
        min_time = event_time - self.window_size
        self._events[key] = [
            (t, ev) for t, ev in self._events[key] if t >= min_time
        ]

        return closed

    def flush(self, key: str = "") -> list[WindowResult]:
        """Force-emit a window containing all remaining events."""
        if key not in self._events or not self._events[key]:
            return []
        events = [ev for _, ev in self._events[key]]
        times = [t for t, _ in self._events[key]]
        result = [WindowResult(
            window_start=min(times),
            window_end=max(times) + 0.001,
            events=events,
            key=key,
        )]
        self._events[key] = []
        return result


class SessionWindow:
    """Gap-based session windows.

    A session closes when no event arrives within ``gap_seconds`` of the
    last event in the session. Sessions are keyed by an arbitrary string.
    """

    def __init__(self, gap_seconds: float):
        self.gap = gap_seconds
        # key -> [(event_time, event)]
        self._sessions: dict[str, list[tuple[float, dict]]] = defaultdict(list)
        # key -> last event time
        self._last_time: dict[str, float] = {}

    def add(self, event: dict[str, Any], event_time: float, key: str = "") -> list[WindowResult]:
        """Add an event. Returns closed sessions if gap exceeded."""
        closed = []

        if key in self._last_time:
            last = self._last_time[key]
            if event_time - last >= self.gap:
                # Gap exceeded — close the current session
                session_events = self._sessions.pop(key, [])
                if session_events:
                    times = [t for t, _ in session_events]
                    closed.append(WindowResult(
                        window_start=min(times),
                        window_end=max(times),
                        events=[ev for _, ev in session_events],
                        key=key,
                    ))

        self._sessions[key].append((event_time, event))
        self._last_time[key] = event_time
        return closed

    def flush(self, key: str = "") -> list[WindowResult]:
        """Force-close the session for a key."""
        session_events = self._sessions.pop(key, [])
        self._last_time.pop(key, None)
        if not session_events:
            return []
        times = [t for t, _ in session_events]
        return [WindowResult(
            window_start=min(times),
            window_end=max(times),
            events=[ev for _, ev in session_events],
            key=key,
        )]

    def flush_all(self) -> list[WindowResult]:
        """Force-close all sessions."""
        closed = []
        for key in list(self._sessions.keys()):
            closed.extend(self.flush(key))
        return closed
