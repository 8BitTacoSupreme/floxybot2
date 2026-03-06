"""Tests for Intercom bridge."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.escalation.intercom import create_ticket, should_escalate


@pytest.mark.asyncio
async def test_no_api_key_returns_stub():
    """Without INTERCOM_API_KEY, returns stub response."""
    with patch("src.config.settings") as mock_settings:
        mock_settings.INTERCOM_API_KEY = ""
        mock_settings.INTERCOM_API_URL = "https://api.intercom.io"

        result = await create_ticket(
            message={"content": {"text": "help"}, "user_identity": {}},
            context={},
            entitlement_tier="community",
        )
        assert result["status"] == "escalated"
        assert result["ticket_id"] is None


@pytest.mark.asyncio
async def test_pro_tier_includes_full_context():
    """Pro tier ticket includes sanitized context."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"conversation_id": "conv_123"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.config.settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_client):
        mock_settings.INTERCOM_API_KEY = "test-key"
        mock_settings.INTERCOM_API_URL = "https://api.intercom.io"

        result = await create_ticket(
            message={"content": {"text": "help me"}, "user_identity": {"email": "user@test.com"}},
            context={"project": {"detected_skills": ["k8s"]}, "conversation_id": "conv_1"},
            entitlement_tier="pro",
        )
        assert result["status"] == "escalated"
        assert result["ticket_id"] == "conv_123"

        # Verify the POST was made with context in body
        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert "Context" in body["body"]
        assert "k8s" in body["body"]


@pytest.mark.asyncio
async def test_community_tier_basic_ticket():
    """Community tier gets basic ticket without full context."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "basic_123"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.config.settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_client):
        mock_settings.INTERCOM_API_KEY = "test-key"
        mock_settings.INTERCOM_API_URL = "https://api.intercom.io"

        result = await create_ticket(
            message={"content": {"text": "help"}, "user_identity": {}},
            context={"project": {"detected_skills": ["k8s"]}},
            entitlement_tier="community",
        )
        assert result["status"] == "escalated"

        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert "Context" not in body["body"]


@pytest.mark.asyncio
async def test_api_error_graceful_failure():
    """API errors return a graceful fallback response."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.config.settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_client):
        mock_settings.INTERCOM_API_KEY = "test-key"
        mock_settings.INTERCOM_API_URL = "https://api.intercom.io"

        result = await create_ticket(
            message={"content": {"text": "help"}, "user_identity": {}},
            context={},
            entitlement_tier="pro",
        )
        assert result["status"] == "escalated"
        assert result["ticket_id"] is None


@pytest.mark.asyncio
async def test_context_is_sanitized():
    """Context with secrets is sanitized before sending to Intercom."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "ticket_1"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.config.settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_client):
        mock_settings.INTERCOM_API_KEY = "test-key"
        mock_settings.INTERCOM_API_URL = "https://api.intercom.io"

        context = {
            "project": {"detected_skills": ["aws"]},
            "env": {"API_KEY": "sk-secret-123"},
        }

        result = await create_ticket(
            message={"content": {"text": "help"}, "user_identity": {"email": "u@t.com"}},
            context=context,
            entitlement_tier="enterprise",
        )
        assert result["status"] == "escalated"
        # The original context should not have been sent with the secret
        call_args = mock_client.post.call_args
        body_text = call_args.kwargs.get("json", call_args[1].get("json", {}))["body"]
        assert "sk-secret-123" not in body_text
