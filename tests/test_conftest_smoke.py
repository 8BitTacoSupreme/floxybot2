"""Smoke test that each fixture instantiates without error."""

from __future__ import annotations


def test_sample_message(sample_message):
    assert "message_id" in sample_message
    assert sample_message["user_identity"]["channel"] == "cli"
    assert sample_message["content"]["text"]


def test_in_memory_publisher(in_memory_publisher):
    assert in_memory_publisher is not None
    assert hasattr(in_memory_publisher, "events")


def test_mock_redis(mock_redis):
    assert mock_redis is not None


def test_mock_claude(mock_claude):
    assert mock_claude is not None


def test_mock_voyage(mock_voyage):
    assert mock_voyage is not None
