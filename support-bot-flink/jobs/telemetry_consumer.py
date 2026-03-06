"""Telemetry aggregation consumer.

Consumes ``floxbot.copilot.telemetry`` and produces:
- Tumbling 1h window: per-mode counts, avg session duration, per-skill usage
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from consumer_base import StreamConsumer
from windows import TumblingWindow

logger = logging.getLogger(__name__)


class TelemetryConsumer(StreamConsumer):
    """Aggregates copilot telemetry using tumbling 1h windows."""

    def __init__(self):
        super().__init__(
            topics=["floxbot.copilot.telemetry"],
            group_id="telemetry-aggregation",
        )
        self._tumbling = TumblingWindow(window_size_seconds=3600)  # 1h

    def process_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        outputs = []
        event_time = event.get("timestamp", 0.0)

        tumbling_results = self._tumbling.add(event, event_time)

        for wr in tumbling_results:
            agg = self._aggregate(wr.events)
            outputs.append({
                "type": "hourly_telemetry_aggregate",
                "window_start": wr.window_start,
                "window_end": wr.window_end,
                **agg,
            })

        return outputs

    def flush(self) -> list[dict[str, Any]]:
        outputs = []
        for wr in self._tumbling.flush_all():
            agg = self._aggregate(wr.events)
            outputs.append({"type": "hourly_telemetry_aggregate", **agg})
        return outputs

    @staticmethod
    def _aggregate(events: list[dict]) -> dict:
        mode_counts: Counter = Counter()
        skill_counts: Counter = Counter()
        durations: list[float] = []

        for ev in events:
            mode = ev.get("mode", "unknown")
            mode_counts[mode] += 1

            for skill in ev.get("skills", []):
                skill_counts[skill] += 1

            duration = ev.get("duration_seconds")
            if duration is not None:
                durations.append(float(duration))

        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "mode_counts": dict(mode_counts),
            "skill_counts": dict(skill_counts),
            "avg_duration_seconds": round(avg_duration, 2),
            "total_events": len(events),
        }
