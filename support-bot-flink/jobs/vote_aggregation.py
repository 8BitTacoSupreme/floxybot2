"""Vote aggregation consumer.

Consumes ``floxbot.votes`` and produces:
- Tumbling 1h window: per-skill vote counts, per-topic vote counts
- Sliding 24h window (1h slide): per-user satisfaction trend, anomaly detection
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from consumer_base import StreamConsumer
from windows import SlidingWindow, TumblingWindow

logger = logging.getLogger(__name__)

# Anomaly threshold: downvote rate > 2x baseline
ANOMALY_DOWNVOTE_MULTIPLIER = 2.0
DEFAULT_BASELINE_DOWNVOTE_RATE = 0.15  # 15% baseline


class VoteAggregationConsumer(StreamConsumer):
    """Aggregates votes using tumbling 1h and sliding 24h windows."""

    def __init__(self):
        super().__init__(topics=["floxbot.votes"], group_id="vote-aggregation")
        self._tumbling = TumblingWindow(window_size_seconds=3600)  # 1h
        self._sliding = SlidingWindow(window_size_seconds=86400, slide_seconds=3600)  # 24h/1h

    def process_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        outputs = []
        event_time = event.get("timestamp", 0.0)
        user_id = event.get("user_id", "unknown")

        # Feed both windows
        tumbling_results = self._tumbling.add(event, event_time)
        sliding_results = self._sliding.add(event, event_time, key="global")

        # Process tumbling window closures (1h aggregates)
        for wr in tumbling_results:
            agg = self._aggregate_hourly(wr.events)
            outputs.append({
                "type": "hourly_vote_aggregate",
                "window_start": wr.window_start,
                "window_end": wr.window_end,
                **agg,
            })

        # Process sliding window closures (24h trend)
        for wr in sliding_results:
            trend = self._compute_trend(wr.events)
            outputs.append({
                "type": "daily_vote_trend",
                "window_start": wr.window_start,
                "window_end": wr.window_end,
                **trend,
            })

        return outputs

    def flush(self) -> list[dict[str, Any]]:
        outputs = []
        for wr in self._tumbling.flush_all():
            agg = self._aggregate_hourly(wr.events)
            outputs.append({"type": "hourly_vote_aggregate", **agg})
        for wr in self._sliding.flush("global"):
            trend = self._compute_trend(wr.events)
            outputs.append({"type": "daily_vote_trend", **trend})
        return outputs

    @staticmethod
    def _aggregate_hourly(events: list[dict]) -> dict:
        skill_votes: Counter = Counter()
        topic_votes: Counter = Counter()
        upvotes = 0
        downvotes = 0

        for ev in events:
            skill = ev.get("skill", "unknown")
            topic = ev.get("topic", "general")
            vote = ev.get("vote", "up")

            skill_votes[skill] += 1
            topic_votes[topic] += 1
            if vote == "up":
                upvotes += 1
            else:
                downvotes += 1

        return {
            "skill_votes": dict(skill_votes),
            "topic_votes": dict(topic_votes),
            "upvotes": upvotes,
            "downvotes": downvotes,
            "total": len(events),
        }

    @staticmethod
    def _compute_trend(events: list[dict]) -> dict:
        user_satisfaction: dict[str, list] = {}
        total_down = 0
        total = len(events)

        for ev in events:
            user = ev.get("user_id", "unknown")
            vote = ev.get("vote", "up")
            user_satisfaction.setdefault(user, []).append(vote)
            if vote == "down":
                total_down += 1

        downvote_rate = total_down / total if total > 0 else 0.0
        anomaly = downvote_rate > (DEFAULT_BASELINE_DOWNVOTE_RATE * ANOMALY_DOWNVOTE_MULTIPLIER)

        return {
            "total_votes": total,
            "downvote_rate": round(downvote_rate, 3),
            "anomaly_detected": anomaly,
            "user_count": len(user_satisfaction),
        }
