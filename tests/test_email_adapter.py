"""Tests for the email adapter — normalizer, formatter, and handler."""

from __future__ import annotations

import pytest

from src.normalizer import normalize_email
from src.formatter import format_reply


class TestEmailNormalizer:
    """Test email normalization to canonical schema."""

    def test_basic_email(self):
        form = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Help with flox",
            "text": "How do I install packages?",
            "headers": "",
        }
        result = normalize_email(form)
        assert result["user_identity"]["channel"] == "email"
        assert result["user_identity"]["email"] == "user@example.com"
        assert "Help with flox" in result["content"]["text"]

    def test_name_angle_bracket_format(self):
        form = {
            "from": "Jane Doe <jane@example.com>",
            "to": "support@flox.dev",
            "subject": "Question",
            "text": "Hello",
            "headers": "",
        }
        result = normalize_email(form)
        assert result["user_identity"]["email"] == "jane@example.com"

    def test_code_block_extraction(self):
        form = {
            "from": "dev@example.com",
            "to": "support@flox.dev",
            "subject": "Error",
            "text": "I see this:\n```\nerror: attribute not found\n```\nHelp?",
            "headers": "",
        }
        result = normalize_email(form)
        assert len(result["content"]["code_blocks"]) == 1
        assert "attribute not found" in result["content"]["code_blocks"][0]

    def test_threading_with_in_reply_to(self):
        form = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Re: Help",
            "text": "Thanks!",
            "headers": "In-Reply-To: <abc123@mail.example.com>\n",
        }
        result = normalize_email(form)
        assert result["context"]["conversation_id"].startswith("email_thread_")

    def test_threading_with_references(self):
        form = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Re: Help",
            "text": "Thanks!",
            "headers": "References: <root@mail.example.com> <reply1@mail.example.com>\n",
        }
        result = normalize_email(form)
        assert result["context"]["conversation_id"].startswith("email_thread_")

    def test_no_threading_uses_subject(self):
        form = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Unique question",
            "text": "How?",
            "headers": "",
        }
        result = normalize_email(form)
        assert result["context"]["conversation_id"].startswith("email_subject_")

    def test_html_fallback(self):
        form = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Test",
            "text": "",
            "html": "<p>Hello <b>world</b></p>",
            "headers": "",
        }
        result = normalize_email(form)
        assert "Hello" in result["content"]["text"]
        # HTML tags should be stripped
        assert "<p>" not in result["content"]["text"]

    def test_subject_in_content(self):
        form = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Manifest error",
            "text": "My env won't activate",
            "headers": "",
        }
        result = normalize_email(form)
        assert "Manifest error" in result["content"]["text"]

    def test_session_defaults(self):
        form = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Q",
            "text": "Hi",
            "headers": "",
        }
        result = normalize_email(form)
        assert result["session"]["prior_messages"] == 0
        assert result["session"]["copilot_active"] is False


class TestEmailFormatter:
    """Test response formatting for email replies."""

    def test_basic_reply(self):
        reply = format_reply("Hello world", "Original subject")
        assert reply["subject"] == "Re: Original subject"
        assert "Hello world" in reply["html"]

    def test_re_prefix_not_doubled(self):
        reply = format_reply("Response", "Re: Already replied")
        assert reply["subject"] == "Re: Already replied"

    def test_code_blocks_formatted(self):
        reply = format_reply("Try:\n```bash\nflox install hello\n```", "Help")
        assert "<pre" in reply["html"]
        assert "flox install hello" in reply["html"]

    def test_inline_code(self):
        reply = format_reply("Use `flox activate` to start", "Help")
        assert "<code" in reply["html"]

    def test_sources_included(self):
        reply = format_reply("Answer", "Q", sources=["Flox Docs", "Blog Post"])
        assert "Sources:" in reply["html"]
        assert "Flox Docs" in reply["html"]

    def test_footer_present(self):
        reply = format_reply("Answer", "Q")
        assert "FloxBot Support" in reply["html"]
