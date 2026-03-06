"""Cross-channel session correlation consumer.

Consumes ``floxbot.messages.inbound`` and detects when the same user
interacts across multiple channels within a session window (30-min gap).
Emits cross-channel events to ``floxbot.sessions.xc``.
"""

from __future__ import annotations

import logging
from typing import Any

from consumer_base import StreamConsumer
from windows import SessionWindow

logger = logging.getLogger(__name__)


class CrossChannelConsumer(StreamConsumer):
    """Detects cross-channel sessions via session windows."""

    def __init__(self):
        super().__init__(
            topics=["floxbot.messages.inbound"],
            group_id="xc-correlation",
        )
        self._session = SessionWindow(gap_seconds=1800)  # 30 min

    def process_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        user_id = (
            event.get("user_identity", {}).get("canonical_user_id")
            or event.get("user_id", "unknown")
        )
        event_time = event.get("timestamp", 0.0)

        closed = self._session.add(event, event_time, key=user_id)
        return self._check_cross_channel(closed)

    def flush(self) -> list[dict[str, Any]]:
        closed = self._session.flush_all()
        return self._check_cross_channel(closed)

    def _check_cross_channel(self, closed_sessions: list) -> list[dict[str, Any]]:
        outputs = []
        for wr in closed_sessions:
            channels = set()
            keywords = []
            for ev in wr.events:
                ch = (
                    ev.get("user_identity", {}).get("channel")
                    or ev.get("channel", "unknown")
                )
                channels.add(ch)
                text = ev.get("content", {}).get("text", "")
                if text:
                    keywords.extend(self._extract_keywords(text))

            if len(channels) >= 2:
                # Compute keyword overlap
                keyword_counts: dict[str, int] = {}
                for kw in keywords:
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
                overlapping = [kw for kw, c in keyword_counts.items() if c > 1]

                outputs.append({
                    "type": "cross_channel_session",
                    "topic": "floxbot.sessions.xc",
                    "user_id": wr.key,
                    "channels": sorted(channels),
                    "topic_overlap": overlapping[:10],
                    "session_duration": wr.window_end - wr.window_start,
                    "event_count": len(wr.events),
                })
        return outputs

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Simple keyword extraction — split on whitespace, lowercase, filter short."""
        words = text.lower().split()
        return [w for w in words if len(w) > 3 and w.isalpha()]
