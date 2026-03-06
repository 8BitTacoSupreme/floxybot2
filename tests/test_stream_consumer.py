"""Tests for streaming consumer base and windowing library."""

from __future__ import annotations

import pytest

from consumer_base import StreamConsumer
from windows import SessionWindow, SlidingWindow, TumblingWindow


# --- Tumbling Window ---


def test_tumbling_buckets_events():
    """Events in the same time bucket are grouped together."""
    tw = TumblingWindow(window_size_seconds=3600)  # 1h
    # Add events at t=100, t=200 (same bucket 0)
    r1 = tw.add({"v": 1}, event_time=100.0)
    r2 = tw.add({"v": 2}, event_time=200.0)
    assert r1 == []
    assert r2 == []

    # Add event in next bucket — closes bucket 0
    r3 = tw.add({"v": 3}, event_time=3700.0)
    assert len(r3) == 1
    assert len(r3[0].events) == 2
    assert r3[0].window_start == 0.0
    assert r3[0].window_end == 3600.0


def test_tumbling_flush():
    """Flush closes all open windows."""
    tw = TumblingWindow(window_size_seconds=3600)
    tw.add({"v": 1}, event_time=100.0)
    tw.add({"v": 2}, event_time=3700.0)
    results = tw.flush_all()
    # Should close bucket for t=3700
    assert len(results) == 1
    assert results[0].events == [{"v": 2}]


# --- Sliding Window ---


def test_sliding_emits_overlapping_aggregates():
    """Sliding window emits overlapping results."""
    sw = SlidingWindow(window_size_seconds=4.0, slide_seconds=2.0)
    # Add events spaced apart
    r1 = sw.add({"v": 1}, event_time=0.0)
    r2 = sw.add({"v": 2}, event_time=1.0)
    r3 = sw.add({"v": 3}, event_time=3.0)
    # At t=5, first window [0,4) should close
    r4 = sw.add({"v": 4}, event_time=5.0)

    # Should have emitted at least one window
    all_results = r1 + r2 + r3 + r4
    assert len(all_results) >= 1
    # The first window should contain events from [0, 4)
    first_window = all_results[0]
    assert len(first_window.events) >= 1


# --- Session Window ---


def test_session_detects_gap():
    """Session closes when gap exceeds threshold."""
    sw = SessionWindow(gap_seconds=1800)  # 30 min
    r1 = sw.add({"v": 1}, event_time=0.0, key="user1")
    r2 = sw.add({"v": 2}, event_time=600.0, key="user1")  # 10 min later
    assert r1 == []
    assert r2 == []

    # 31 min gap — session should close
    r3 = sw.add({"v": 3}, event_time=2400.0, key="user1")
    assert len(r3) == 1
    assert len(r3[0].events) == 2  # v1 and v2
    assert r3[0].key == "user1"


def test_session_no_close_within_gap():
    """Events within gap don't close the session."""
    sw = SessionWindow(gap_seconds=1800)
    sw.add({"v": 1}, event_time=0.0, key="u1")
    sw.add({"v": 2}, event_time=900.0, key="u1")  # 15 min
    sw.add({"v": 3}, event_time=1700.0, key="u1")  # 28 min from v2

    # Flush to check — all 3 in one session
    results = sw.flush("u1")
    assert len(results) == 1
    assert len(results[0].events) == 3


# --- Consumer Base ---


class SampleConsumer(StreamConsumer):
    """Concrete consumer for testing."""

    def __init__(self):
        super().__init__(topics=["test.topic"], group_id="test-group")
        self._received = []

    def process_event(self, event):
        self._received.append(event)
        return [{"processed": event.get("id", "?")}]

    def flush(self):
        return [{"flushed": len(self._received)}]


@pytest.mark.asyncio
async def test_consumer_processes_events():
    """Consumer processes a batch of events and flushes."""
    consumer = SampleConsumer()
    events = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    outputs = await consumer.run_on_events(events)

    # 3 process outputs + 1 flush output
    assert len(outputs) == 4
    assert outputs[0] == {"processed": "a"}
    assert outputs[3] == {"flushed": 3}
