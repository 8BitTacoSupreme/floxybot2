"""Tests for telemetry consumer."""

from __future__ import annotations

import time

import pytest

from jobs.telemetry_consumer import TelemetryConsumer


class TestTelemetryConsumer:
    def test_topics_and_group(self):
        c = TelemetryConsumer()
        assert c.topics == ["floxbot.copilot.telemetry"]
        assert c.group_id == "telemetry-aggregation"

    @pytest.mark.asyncio
    async def test_mode_counts_aggregate(self):
        c = TelemetryConsumer()
        base = 1000000.0
        events = [
            {"timestamp": base, "mode": "ask", "skills": ["core-canon"], "duration_seconds": 5.0},
            {"timestamp": base + 10, "mode": "ask", "skills": ["core-canon"], "duration_seconds": 3.0},
            {"timestamp": base + 20, "mode": "chat", "skills": ["k8s"], "duration_seconds": 10.0},
        ]
        results = await c.run_on_events(events)
        assert len(results) >= 1
        agg = results[0]
        assert agg["mode_counts"]["ask"] == 2
        assert agg["mode_counts"]["chat"] == 1

    @pytest.mark.asyncio
    async def test_avg_duration_computed(self):
        c = TelemetryConsumer()
        base = 1000000.0
        events = [
            {"timestamp": base, "mode": "ask", "duration_seconds": 4.0},
            {"timestamp": base + 10, "mode": "ask", "duration_seconds": 6.0},
        ]
        results = await c.run_on_events(events)
        agg = results[0]
        assert agg["avg_duration_seconds"] == 5.0

    @pytest.mark.asyncio
    async def test_skill_counts_aggregate(self):
        c = TelemetryConsumer()
        base = 1000000.0
        events = [
            {"timestamp": base, "mode": "ask", "skills": ["core-canon", "k8s"]},
            {"timestamp": base + 10, "mode": "chat", "skills": ["k8s"]},
        ]
        results = await c.run_on_events(events)
        agg = results[0]
        assert agg["skill_counts"]["k8s"] == 2
        assert agg["skill_counts"]["core-canon"] == 1

    @pytest.mark.asyncio
    async def test_flush_returns_results(self):
        c = TelemetryConsumer()
        base = 1000000.0
        # Add events but don't trigger window closure
        c.process_event({"timestamp": base, "mode": "diagnose", "duration_seconds": 12.0})
        results = c.flush()
        assert len(results) == 1
        assert results[0]["total_events"] == 1
