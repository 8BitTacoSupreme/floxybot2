"""Central API configuration singleton.

This is the module that all API code imports as ``from src.config import settings``.
Reads from environment variables with sensible defaults, matching the pattern in
``support-bot-shared/src/config/settings.py``.
"""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Settings read from environment variables at instantiation time."""

    def __init__(self) -> None:
        # LLM backends
        self.CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
        self.CLAUDE_MODEL = os.environ.get("FLOXBOT_CLAUDE_MODEL", "claude-sonnet-4-6")
        self.CODEX_API_KEY = os.environ.get("FLOXBOT_CODEX_API_KEY", "")
        self.CODEX_MODEL = os.environ.get("FLOXBOT_CODEX_MODEL", "claude-sonnet-4-6")

        # Voyage embeddings
        self.VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
        self.EMBEDDING_MODEL = os.environ.get("FLOXBOT_EMBEDDING_MODEL", "voyage-3-lite")
        self.EMBEDDING_DIMENSIONS = int(os.environ.get("FLOXBOT_EMBEDDING_DIMENSION", "512"))

        # Database
        self.DATABASE_URL = os.environ.get(
            "FLOXBOT_DATABASE_URL",
            "postgresql+asyncpg://floxbot:floxbot@localhost:5432/floxbot",
        )

        # Redis
        self.REDIS_URL = os.environ.get("FLOXBOT_REDIS_URL", "redis://localhost:6379/0")

        # Kafka
        self.KAFKA_BOOTSTRAP = os.environ.get("FLOXBOT_KAFKA_BOOTSTRAP", "localhost:9092")

        # RAG
        self.RAG_TOP_K = int(os.environ.get("FLOXBOT_RAG_TOP_K", "5"))
        self.RAG_SIMILARITY_THRESHOLD = float(
            os.environ.get("FLOXBOT_RAG_SIMILARITY_THRESHOLD", "0.3")
        )

        # Skills
        self.SKILLS_PATH = os.environ.get("FLOXBOT_SKILLS_PATH", "./skills")
        self.CUSTOM_SKILLS_PATH = os.environ.get("FLOXBOT_CUSTOM_SKILLS_PATH", "./custom-skills")
        self.MAX_SKILLS_PER_TURN = 2
        self.PRIMARY_SKILL_TOKEN_BUDGET = 8000
        self.SECONDARY_SKILL_TOKEN_BUDGET = 4000

        # Entitlement override (dev/test)
        self.TIER_OVERRIDE = os.environ.get("FLOXBOT_TIER_OVERRIDE", "")
        self.FLOXBOT_TIER_OVERRIDE = self.TIER_OVERRIDE

        # MCP tool timeout (seconds)
        self.MCP_TOOL_TIMEOUT = int(os.environ.get("FLOXBOT_MCP_TOOL_TIMEOUT", "15"))

        # Dev mode
        self.DEV_TOKEN = os.environ.get("FLOXBOT_DEV_TOKEN", "")

        # FloxHub
        self.FLOXHUB_AUTH_DIR = os.environ.get(
            "FLOXHUB_AUTH_DIR", str(Path.home() / ".flox")
        )
        self.FLOXHUB_API_URL = os.environ.get(
            "FLOXHUB_API_URL", "https://hub.flox.dev/api/v1"
        )

        # Entitlement cache
        self.ENTITLEMENT_CACHE_TTL = int(
            os.environ.get("FLOXBOT_ENTITLEMENT_CACHE_TTL", "3600")
        )

        # Intercom
        self.INTERCOM_API_KEY = os.environ.get("FLOXBOT_INTERCOM_API_KEY", "")
        self.INTERCOM_API_URL = os.environ.get(
            "FLOXBOT_INTERCOM_API_URL", "https://api.intercom.io"
        )


settings = Settings()
