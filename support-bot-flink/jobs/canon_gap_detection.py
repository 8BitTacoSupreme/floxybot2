"""Canon gap detection consumer.

Consumes ``floxbot.votes`` and ``floxbot.context.detected``.
Daily tumbling window that clusters downvoted queries by skill
and flags skills with >30% downvote rate.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from consumer_base import StreamConsumer
from windows import TumblingWindow

logger = logging.getLogger(__name__)

GAP_DOWNVOTE_THRESHOLD = 0.30  # 30% downvote rate


class CanonGapConsumer(StreamConsumer):
    """Detects canon gaps via daily vote/context aggregation."""

    def __init__(self):
        super().__init__(
            topics=["floxbot.votes", "floxbot.context.detected"],
            group_id="canon-gap-detection",
        )
        self._window = TumblingWindow(window_size_seconds=86400)  # 1 day

    def process_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        event_time = event.get("timestamp", 0.0)
        closed = self._window.add(event, event_time)
        return self._analyze_gaps(closed)

    def flush(self) -> list[dict[str, Any]]:
        closed = self._window.flush_all()
        return self._analyze_gaps(closed)

    def _analyze_gaps(self, closed_windows: list) -> list[dict[str, Any]]:
        outputs = []
        for wr in closed_windows:
            skill_total: Counter = Counter()
            skill_downvotes: Counter = Counter()

            for ev in wr.events:
                skill = ev.get("skill", ev.get("skills", ["unknown"])[0] if isinstance(ev.get("skills"), list) else "unknown")
                skill_total[skill] += 1
                if ev.get("vote") == "down":
                    skill_downvotes[skill] += 1

            flagged_skills = []
            for skill, total in skill_total.items():
                if total == 0:
                    continue
                rate = skill_downvotes[skill] / total
                if rate > GAP_DOWNVOTE_THRESHOLD:
                    flagged_skills.append({
                        "skill": skill,
                        "total": total,
                        "downvotes": skill_downvotes[skill],
                        "downvote_rate": round(rate, 3),
                    })

            if flagged_skills:
                outputs.append({
                    "type": "canon_gap_detected",
                    "window_start": wr.window_start,
                    "window_end": wr.window_end,
                    "flagged_skills": flagged_skills,
                })
        return outputs
