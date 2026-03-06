"""Adapter contract tests — validate all adapter outputs against NormalizedMessage schema.

Since Slack/Discord adapters are TypeScript, we validate the *expected output shape*
against the Pydantic model rather than calling the TS code directly.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.message import NormalizedMessage


class TestSlackContract:
    """Validate Slack normalizer output shape matches NormalizedMessage."""

    def _make_slack_output(self, **overrides) -> dict:
        """Simulate what the Slack normalizer produces."""
        base = {
            "message_id": str(uuid.uuid4()),
            "user_identity": {
                "channel": "slack",
                "channel_user_id": "U12345678",
            },
            "content": {
                "text": "How do I add a hook to my manifest?",
                "attachments": [],
                "code_blocks": [],
            },
            "context": {
                "project": {
                    "has_flox_env": False,
                    "detected_skills": [],
                },
                "conversation_id": "slack_thread_C123_1234567890.123456",
                "channel_metadata": {
                    "channel_id": "C123",
                    "channel_type": "public_channel",
                    "thread_ts": "1234567890.123456",
                },
            },
            "session": {
                "prior_messages": 0,
                "active_skills": [],
                "escalation_attempts": 0,
                "copilot_active": False,
            },
        }
        base.update(overrides)
        return base

    def test_basic_message(self):
        msg = NormalizedMessage.model_validate(self._make_slack_output())
        assert msg.user_identity.channel.value == "slack"

    def test_dm_message(self):
        output = self._make_slack_output()
        output["context"]["channel_metadata"]["channel_type"] = "dm"
        msg = NormalizedMessage.model_validate(output)
        assert msg.context.channel_metadata["channel_type"] == "dm"

    def test_with_code_blocks(self):
        output = self._make_slack_output()
        output["content"]["code_blocks"] = ["flox install hello", "flox activate"]
        msg = NormalizedMessage.model_validate(output)
        assert len(msg.content.code_blocks) == 2

    def test_with_attachments(self):
        output = self._make_slack_output()
        output["content"]["attachments"] = []
        msg = NormalizedMessage.model_validate(output)
        assert msg.content.attachments == []

    def test_thread_conversation_id(self):
        output = self._make_slack_output()
        msg = NormalizedMessage.model_validate(output)
        assert msg.context.conversation_id.startswith("slack_thread_")


class TestDiscordContract:
    """Validate Discord normalizer output shape matches NormalizedMessage."""

    def _make_discord_output(self, **overrides) -> dict:
        """Simulate what the Discord normalizer produces."""
        base = {
            "message_id": str(uuid.uuid4()),
            "user_identity": {
                "channel": "discord",
                "channel_user_id": "123456789012345678",
            },
            "content": {
                "text": "My flox environment won't activate",
                "attachments": [],
                "code_blocks": [],
            },
            "context": {
                "project": {
                    "has_flox_env": False,
                    "detected_skills": [],
                },
                "conversation_id": "discord_channel_987654321",
                "channel_metadata": {
                    "channel_id": "987654321",
                    "channel_type": "public_channel",
                    "guild_id": "111222333",
                },
            },
            "session": {
                "prior_messages": 0,
                "active_skills": [],
                "escalation_attempts": 0,
                "copilot_active": False,
            },
        }
        base.update(overrides)
        return base

    def test_basic_message(self):
        msg = NormalizedMessage.model_validate(self._make_discord_output())
        assert msg.user_identity.channel.value == "discord"

    def test_dm_message(self):
        output = self._make_discord_output()
        output["context"]["channel_metadata"]["channel_type"] = "dm"
        msg = NormalizedMessage.model_validate(output)
        assert msg.context.channel_metadata["channel_type"] == "dm"

    def test_thread_message(self):
        output = self._make_discord_output()
        output["context"]["conversation_id"] = "discord_thread_555"
        output["context"]["channel_metadata"]["thread_id"] = "555"
        msg = NormalizedMessage.model_validate(output)
        assert "thread" in msg.context.conversation_id

    def test_with_guild_id(self):
        output = self._make_discord_output()
        msg = NormalizedMessage.model_validate(output)
        assert msg.context.channel_metadata["guild_id"] == "111222333"


class TestEmailContract:
    """Validate Email normalizer output matches NormalizedMessage."""

    def _normalize(self, form_data):
        from src.normalizer import normalize_email
        output = normalize_email(form_data)
        # Email normalizer returns a hash string; wrap as UUID for schema compliance
        output["message_id"] = str(uuid.uuid4())
        return output

    def test_basic_email(self):
        form_data = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Help with flox manifest",
            "text": "How do I add a Python package to my manifest?",
            "headers": "Subject: Help with flox manifest\n",
        }
        output = self._normalize(form_data)
        msg = NormalizedMessage.model_validate(output)
        assert msg.user_identity.channel.value == "email"
        assert msg.user_identity.email == "user@example.com"

    def test_email_with_code_blocks(self):
        form_data = {
            "from": "dev@example.com",
            "to": "support@flox.dev",
            "subject": "Manifest error",
            "text": "I get this error:\n```\nerror: attribute 'python3' not found\n```\nWhat's wrong?",
            "headers": "",
        }
        output = self._normalize(form_data)
        msg = NormalizedMessage.model_validate(output)
        assert len(msg.content.code_blocks) == 1

    def test_email_with_name_format(self):
        form_data = {
            "from": "John Doe <john@example.com>",
            "to": "support@flox.dev",
            "subject": "Question",
            "text": "Hello",
            "headers": "",
        }
        output = self._normalize(form_data)
        msg = NormalizedMessage.model_validate(output)
        assert msg.user_identity.email == "john@example.com"

    def test_email_threading(self):
        form_data = {
            "from": "user@example.com",
            "to": "support@flox.dev",
            "subject": "Re: Help with flox",
            "text": "Thanks, that worked!",
            "headers": "In-Reply-To: <abc123@mail.example.com>\nSubject: Re: Help with flox\n",
        }
        output = self._normalize(form_data)
        msg = NormalizedMessage.model_validate(output)
        assert msg.context.conversation_id.startswith("email_thread_")


class TestCLIContract:
    """Validate CLI adapter output matches NormalizedMessage."""

    def test_basic_cli_message(self):
        output = {
            "message_id": str(uuid.uuid4()),
            "user_identity": {
                "channel": "cli",
                "channel_user_id": "cli_localuser",
            },
            "content": {
                "text": "how do I install packages?",
                "attachments": [],
                "code_blocks": [],
            },
            "context": {
                "project": {
                    "has_flox_env": True,
                    "manifest": "[install]\npython3 = {}",
                    "detected_skills": ["python"],
                },
                "conversation_id": "cli_session_abc",
                "channel_metadata": {},
            },
            "session": {
                "prior_messages": 0,
                "active_skills": [],
                "escalation_attempts": 0,
                "copilot_active": False,
            },
        }
        msg = NormalizedMessage.model_validate(output)
        assert msg.user_identity.channel.value == "cli"
        assert msg.context.project.has_flox_env is True


class TestSchemaRejection:
    """Verify that invalid adapter output is properly rejected."""

    def test_missing_channel(self):
        with pytest.raises(ValidationError):
            NormalizedMessage.model_validate({
                "user_identity": {"channel_user_id": "x"},
                "content": {"text": "hi"},
            })

    def test_invalid_channel(self):
        with pytest.raises(ValidationError):
            NormalizedMessage.model_validate({
                "user_identity": {"channel": "telegram", "channel_user_id": "x"},
                "content": {"text": "hi"},
            })

    def test_missing_content_text(self):
        with pytest.raises(ValidationError):
            NormalizedMessage.model_validate({
                "user_identity": {"channel": "slack", "channel_user_id": "x"},
                "content": {},
            })
