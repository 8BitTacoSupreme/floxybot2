"""Kafka topic definitions for the FloxBot event backbone.

All 9 topics used across the system. Topic names, partition counts,
and retention configs are defined here as the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicConfig:
    """Configuration for a single Kafka topic."""

    name: str
    partitions: int
    retention_ms: int  # -1 = infinite


# --- Topic name constants ---

INBOUND = "floxbot.messages.inbound"
OUTBOUND = "floxbot.messages.outbound"
VOTES = "floxbot.votes"
CONTEXT_DETECTED = "floxbot.context.detected"
ESCALATIONS = "floxbot.escalations"
CANON_UPDATES = "floxbot.canon.updates"
SESSIONS_XC = "floxbot.sessions.xc"
FEEDBACK = "floxbot.feedback"
COPILOT_TELEMETRY = "floxbot.copilot.telemetry"

# --- Full topic configurations ---

TOPIC_CONFIGS: list[TopicConfig] = [
    TopicConfig(name=INBOUND, partitions=6, retention_ms=7 * 86_400_000),         # 7 days
    TopicConfig(name=OUTBOUND, partitions=6, retention_ms=7 * 86_400_000),        # 7 days
    TopicConfig(name=VOTES, partitions=3, retention_ms=30 * 86_400_000),          # 30 days
    TopicConfig(name=CONTEXT_DETECTED, partitions=3, retention_ms=7 * 86_400_000),# 7 days
    TopicConfig(name=ESCALATIONS, partitions=2, retention_ms=90 * 86_400_000),    # 90 days
    TopicConfig(name=CANON_UPDATES, partitions=2, retention_ms=-1),               # infinite
    TopicConfig(name=SESSIONS_XC, partitions=3, retention_ms=30 * 86_400_000),    # 30 days
    TopicConfig(name=FEEDBACK, partitions=3, retention_ms=90 * 86_400_000),       # 90 days
    TopicConfig(name=COPILOT_TELEMETRY, partitions=3, retention_ms=14 * 86_400_000),# 14 days
]

ALL_TOPIC_NAMES: list[str] = [tc.name for tc in TOPIC_CONFIGS]
