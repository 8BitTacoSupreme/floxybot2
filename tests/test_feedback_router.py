"""Tests for feedback routing consumer."""

from __future__ import annotations

import pytest

from jobs.feedback_router import CATEGORY_ROUTES, DEFAULT_ROUTE, FeedbackRouterConsumer


def _feedback(category="incorrect", user_id="u1", text="wrong answer"):
    return {"category": category, "user_id": user_id, "text": text, "message_id": "m1"}


@pytest.mark.asyncio
async def test_incorrect_routes_to_doc_gap():
    """'incorrect' feedback routes to doc_gap."""
    consumer = FeedbackRouterConsumer()
    outputs = consumer.process_event(_feedback(category="incorrect"))
    assert len(outputs) == 1
    assert outputs[0]["route"] == "doc_gap"


@pytest.mark.asyncio
async def test_outdated_routes_to_doc_gap():
    """'outdated' feedback routes to doc_gap."""
    consumer = FeedbackRouterConsumer()
    outputs = consumer.process_event(_feedback(category="outdated"))
    assert outputs[0]["route"] == "doc_gap"


@pytest.mark.asyncio
async def test_helpful_routes_to_positive_signal():
    """'helpful' feedback routes to positive_signal."""
    consumer = FeedbackRouterConsumer()
    outputs = consumer.process_event(_feedback(category="helpful"))
    assert outputs[0]["route"] == "positive_signal"


@pytest.mark.asyncio
async def test_all_known_categories_routed():
    """All defined categories route correctly."""
    consumer = FeedbackRouterConsumer()
    for category, expected_route in CATEGORY_ROUTES.items():
        outputs = consumer.process_event(_feedback(category=category))
        assert outputs[0]["route"] == expected_route, f"{category} should route to {expected_route}"


@pytest.mark.asyncio
async def test_unknown_category_routes_to_triage():
    """Unknown category routes to triage_queue."""
    consumer = FeedbackRouterConsumer()
    outputs = consumer.process_event(_feedback(category="banana"))
    assert outputs[0]["route"] == DEFAULT_ROUTE
