"""Tests for Kafka topic definitions."""

from __future__ import annotations

from config.topics import (
    ALL_TOPIC_NAMES,
    CANON_UPDATES,
    CONTEXT_DETECTED,
    COPILOT_TELEMETRY,
    ESCALATIONS,
    FEEDBACK,
    INBOUND,
    OUTBOUND,
    SESSIONS_XC,
    TOPIC_CONFIGS,
    VOTES,
)


def test_nine_topics_defined():
    """All 9 architecture topics are defined."""
    assert len(TOPIC_CONFIGS) == 9
    assert len(ALL_TOPIC_NAMES) == 9


def test_topic_names_match_architecture():
    """Topic names follow the floxbot.* naming convention."""
    expected = {
        "floxbot.messages.inbound",
        "floxbot.messages.outbound",
        "floxbot.votes",
        "floxbot.context.detected",
        "floxbot.escalations",
        "floxbot.canon.updates",
        "floxbot.sessions.xc",
        "floxbot.feedback",
        "floxbot.copilot.telemetry",
    }
    assert set(ALL_TOPIC_NAMES) == expected


def test_constants_match_configs():
    """Name constants match the TOPIC_CONFIGS list."""
    constants = {INBOUND, OUTBOUND, VOTES, CONTEXT_DETECTED, ESCALATIONS,
                 CANON_UPDATES, SESSIONS_XC, FEEDBACK, COPILOT_TELEMETRY}
    config_names = {tc.name for tc in TOPIC_CONFIGS}
    assert constants == config_names


def test_all_topics_have_positive_partitions():
    """Every topic has at least 1 partition."""
    for tc in TOPIC_CONFIGS:
        assert tc.partitions >= 1, f"{tc.name} has {tc.partitions} partitions"


def test_retention_is_set():
    """Every topic has retention configured (positive or -1 for infinite)."""
    for tc in TOPIC_CONFIGS:
        assert tc.retention_ms == -1 or tc.retention_ms > 0, (
            f"{tc.name} has invalid retention {tc.retention_ms}"
        )
