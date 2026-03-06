"""Tests for SLA priority escalation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.escalation.intercom import _resolve_priority, create_ticket


class TestResolvePriority:
    def test_enterprise_urgent(self):
        assert _resolve_priority("enterprise") == "urgent"

    def test_pro_high(self):
        assert _resolve_priority("pro") == "high"

    def test_community_normal(self):
        assert _resolve_priority("community") == "normal"

    def test_unknown_normal(self):
        assert _resolve_priority("unknown") == "normal"

    def test_empty_normal(self):
        assert _resolve_priority("") == "normal"


class TestSLAInTicket:
    @pytest.mark.asyncio
    async def test_enterprise_ticket_has_sla(self):
        """Enterprise tickets include SLA line in body."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "t_1"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.config.settings") as ms, \
             patch("httpx.AsyncClient", return_value=mock_client):
            ms.INTERCOM_API_KEY = "test-key"
            ms.INTERCOM_API_URL = "https://api.intercom.io"

            result = await create_ticket(
                message={"content": {"text": "help"}, "user_identity": {"email": "e@t.com"}},
                context={"project": {"detected_skills": []}},
                entitlement_tier="enterprise",
            )
            assert result["status"] == "escalated"
            call_args = mock_client.post.call_args
            body = call_args.kwargs.get("json", call_args[1].get("json", {}))
            assert "SLA" in body["body"]
            assert body["priority"] == "urgent"

    @pytest.mark.asyncio
    async def test_pro_ticket_no_sla_line(self):
        """Pro tickets don't get the SLA line."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "t_2"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.config.settings") as ms, \
             patch("httpx.AsyncClient", return_value=mock_client):
            ms.INTERCOM_API_KEY = "test-key"
            ms.INTERCOM_API_URL = "https://api.intercom.io"

            await create_ticket(
                message={"content": {"text": "help"}, "user_identity": {"email": "e@t.com"}},
                context={"project": {"detected_skills": []}},
                entitlement_tier="pro",
            )
            call_args = mock_client.post.call_args
            body = call_args.kwargs.get("json", call_args[1].get("json", {}))
            assert "SLA" not in body["body"]
            assert body["priority"] == "high"
