"""Shared httpx API client for Co-Pilot → Central API communication."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .local.config import get_api_url, is_offline, read_floxhub_token

logger = logging.getLogger(__name__)


class CopilotAPIClient:
    """Async HTTP client for the Central API with auth, timeout, and retry."""

    def __init__(self, api_url: str | None = None, token: str | None = None):
        self.api_url = api_url or get_api_url()
        self.token = token or read_floxhub_token()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                headers=headers,
                timeout=10.0,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _is_online(self) -> bool:
        return not is_offline()

    async def post_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/message → bot response."""
        client = await self._get_client()
        resp = await client.post("/v1/message", json=message)
        resp.raise_for_status()
        return resp.json()

    async def get_canon_sync(self, since: str = "2000-01-01T00:00:00Z", skills: str = "") -> list[dict]:
        """GET /v1/canon/sync → list of canon chunks."""
        client = await self._get_client()
        params = {"since": since}
        if skills:
            params["skills"] = skills
        resp = await client.get("/v1/canon/sync", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("chunks", [])

    async def get_memory(self, user_id: str) -> dict[str, Any]:
        """GET /v1/memory/{user_id} → user memory."""
        client = await self._get_client()
        resp = await client.get(f"/v1/memory/{user_id}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("memory", {})

    async def put_memory(self, user_id: str, updates: dict[str, Any]) -> None:
        """PUT /v1/memory/{user_id} → update user memory."""
        client = await self._get_client()
        resp = await client.put(f"/v1/memory/{user_id}", json=updates)
        resp.raise_for_status()

    async def post_votes_batch(self, votes: list[dict]) -> dict[str, Any]:
        """POST /v1/votes/batch → batch vote submission."""
        client = await self._get_client()
        resp = await client.post("/v1/votes/batch", json=votes)
        resp.raise_for_status()
        return resp.json()

    async def post_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/feedback → submit feedback."""
        client = await self._get_client()
        resp = await client.post("/v1/feedback", json=feedback)
        resp.raise_for_status()
        return resp.json()

    async def post_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/tickets → create support ticket."""
        client = await self._get_client()
        resp = await client.post("/v1/tickets", json=ticket)
        resp.raise_for_status()
        return resp.json()

    async def get_entitlements(self) -> dict[str, Any]:
        """GET /v1/entitlements → resolve entitlements."""
        client = await self._get_client()
        resp = await client.get("/v1/entitlements")
        resp.raise_for_status()
        return resp.json()
