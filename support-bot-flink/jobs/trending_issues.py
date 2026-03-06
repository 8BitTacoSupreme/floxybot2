"""Trending issues detection consumer.

Consumes ``floxbot.messages.inbound`` with a sliding 4h window (1h slide).
Groups by keyword clusters and detects spikes (5x increase = trending).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from consumer_base import StreamConsumer
from windows import SlidingWindow

logger = logging.getLogger(__name__)

SPIKE_MULTIPLIER = 5  # 5x increase = trending


class TrendingIssuesConsumer(StreamConsumer):
    """Detects trending issues via keyword spike detection."""

    def __init__(self):
        super().__init__(
            topics=["floxbot.messages.inbound"],
            group_id="trending-issues",
        )
        self._window = SlidingWindow(window_size_seconds=14400, slide_seconds=3600)  # 4h/1h
        self._baseline: Counter = Counter()  # rolling keyword baseline
        self._window_count = 0

    def process_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        event_time = event.get("timestamp", 0.0)
        closed = self._window.add(event, event_time, key="global")
        return self._detect_spikes(closed)

    def flush(self) -> list[dict[str, Any]]:
        closed = self._window.flush("global")
        return self._detect_spikes(closed)

    def _detect_spikes(self, closed_windows: list) -> list[dict[str, Any]]:
        outputs = []
        for wr in closed_windows:
            current: Counter = Counter()
            for ev in wr.events:
                text = ev.get("content", {}).get("text", "")
                keywords = self._extract_keywords(text)
                current.update(keywords)

            # Detect spikes against baseline
            trending = []
            for keyword, count in current.items():
                baseline = self._baseline.get(keyword, 0)
                if baseline > 0 and count >= baseline * SPIKE_MULTIPLIER:
                    trending.append({
                        "keyword": keyword,
                        "current_count": count,
                        "baseline_count": baseline,
                        "multiplier": round(count / baseline, 1),
                    })
                elif baseline == 0 and count >= SPIKE_MULTIPLIER:
                    # New keyword appearing frequently
                    trending.append({
                        "keyword": keyword,
                        "current_count": count,
                        "baseline_count": 0,
                        "multiplier": float(count),
                    })

            if trending:
                outputs.append({
                    "type": "trending_issues",
                    "window_start": wr.window_start,
                    "window_end": wr.window_end,
                    "trending": sorted(trending, key=lambda x: x["current_count"], reverse=True),
                })

            # Update baseline (simple rolling average)
            self._window_count += 1
            for keyword, count in current.items():
                old = self._baseline.get(keyword, 0)
                # Exponential moving average
                self._baseline[keyword] = int(old * 0.7 + count * 0.3)

        return outputs

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Simple keyword extraction."""
        words = text.lower().split()
        return [w for w in words if len(w) > 3 and w.isalpha()]
