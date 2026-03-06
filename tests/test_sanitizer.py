"""Tests for context sanitization."""

from __future__ import annotations

import base64

from src.events.sanitizer import (
    MAX_TEXT_LENGTH,
    sanitize_context,
    sanitize_message_for_event,
)


def test_strips_secret_env_vars():
    """Keys matching SECRET/TOKEN/PASSWORD/API_KEY are redacted."""
    ctx = {
        "env": {
            "API_KEY": "sk-secret-123",
            "DATABASE_PASSWORD": "hunter2",
            "MY_TOKEN": "tok_abc",
            "NORMAL_VAR": "keep-this",
        }
    }
    result = sanitize_context(ctx)
    assert result["env"]["API_KEY"] == "[REDACTED]"
    assert result["env"]["DATABASE_PASSWORD"] == "[REDACTED]"
    assert result["env"]["MY_TOKEN"] == "[REDACTED]"
    assert result["env"]["NORMAL_VAR"] == "keep-this"


def test_preserves_non_secret_vars():
    """Non-sensitive keys are preserved unchanged."""
    ctx = {"project": {"name": "myapp", "version": "1.0"}}
    result = sanitize_context(ctx)
    assert result == ctx


def test_redacts_large_base64_blobs():
    """Base64 blobs > 1KB are redacted."""
    big_blob = base64.b64encode(b"x" * 2000).decode()
    ctx = {"cert": big_blob}
    result = sanitize_context(ctx)
    assert result["cert"] == "[REDACTED_BASE64]"


def test_small_base64_preserved():
    """Small base64 values are kept."""
    small = base64.b64encode(b"hello").decode()
    ctx = {"data": small}
    result = sanitize_context(ctx)
    assert result["data"] == small


def test_scrubs_email_and_ip():
    """Email addresses and IPs are redacted from free text."""
    ctx = {"log": "User user@example.com connected from 192.168.1.100"}
    result = sanitize_context(ctx)
    assert "user@example.com" not in result["log"]
    assert "192.168.1.100" not in result["log"]
    assert "[EMAIL_REDACTED]" in result["log"]
    assert "[IP_REDACTED]" in result["log"]


def test_truncates_long_content():
    """content.text is truncated to MAX_TEXT_LENGTH."""
    msg = {"content": {"text": "a" * 5000}}
    result = sanitize_message_for_event(msg)
    assert len(result["content"]["text"]) < 5000
    assert result["content"]["text"].endswith("...[truncated]")


def test_handles_empty_input():
    """Empty dicts return empty dicts."""
    assert sanitize_context({}) == {}
    assert sanitize_context(None) == {}
    assert sanitize_message_for_event({}) == {}
    assert sanitize_message_for_event(None) == {}


def test_redacts_manifest_vars_secrets():
    """Secret values in [vars] section of manifests are redacted."""
    manifest = """[install]
python3.pkg-path = "python3"

[vars]
NORMAL_VAR = "hello"
MY_SECRET_KEY = "super-secret-value"
API_KEY = "sk-12345"
"""
    ctx = {"manifest": manifest}
    result = sanitize_context(ctx)
    assert "super-secret-value" not in result["manifest"]
    assert "sk-12345" not in result["manifest"]
    assert '"hello"' in result["manifest"]
