"""Tests for CLI adapter."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_cli_build_message():
    """CLI builds a valid normalized message dict."""
    from src.cli import build_message

    msg = build_message("How do I install a package?")
    assert msg["content"]["text"] == "How do I install a package?"
    assert msg["user_identity"]["channel"] == "cli"
    assert "message_id" in msg
    assert "session" in msg


def test_cli_detect_project_context_no_env():
    """No .flox/env/manifest.toml → has_flox_env=False."""
    import os
    from src.cli import detect_project_context

    with tempfile.TemporaryDirectory() as tmpdir:
        orig = os.getcwd()
        try:
            os.chdir(tmpdir)
            ctx = detect_project_context()
        finally:
            os.chdir(orig)
    assert ctx["has_flox_env"] is False


def test_cli_detect_project_context_with_env():
    """With .flox/env/manifest.toml → has_flox_env=True."""
    from src.cli import detect_project_context

    with tempfile.TemporaryDirectory() as tmpdir:
        flox_dir = Path(tmpdir) / ".flox" / "env"
        flox_dir.mkdir(parents=True)
        manifest = flox_dir / "manifest.toml"
        manifest.write_text('[install]\npython3.pkg-path = "python3"\n')

        import os
        orig_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            ctx = detect_project_context()
        finally:
            os.chdir(orig_dir)

    assert ctx["has_flox_env"] is True
    assert "python3" in ctx["manifest"]


def test_cli_ask_sends_request():
    """ask() sends a POST to /v1/message and returns text."""
    from src.cli import ask

    mock_response = MagicMock()
    mock_response.json.return_value = {"text": "Use `flox install python3`."}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = ask("How do I install Python?", api_url="http://test:8000")

    assert result == "Use `flox install python3`."
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "http://test:8000/v1/message"
