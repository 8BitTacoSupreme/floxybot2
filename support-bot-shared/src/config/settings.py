"""Shared configuration settings."""

from __future__ import annotations

import os
from pathlib import Path

# Central API
API_HOST = os.environ.get("FLOXBOT_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("FLOXBOT_API_PORT", "8000"))

# LLM backends
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("FLOXBOT_CLAUDE_MODEL", "claude-sonnet-4-6")
CODEX_API_KEY = os.environ.get("FLOXBOT_CODEX_API_KEY", "")
CODEX_MODEL = os.environ.get("FLOXBOT_CODEX_MODEL", "claude-sonnet-4-6")

# Voyage embeddings
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("FLOXBOT_EMBEDDING_MODEL", "voyage-3-lite")
EMBEDDING_DIMENSION = int(os.environ.get("FLOXBOT_EMBEDDING_DIMENSION", "1024"))

# Kafka
KAFKA_BOOTSTRAP = os.environ.get("FLOXBOT_KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC_PREFIX = os.environ.get("FLOXBOT_KAFKA_TOPIC_PREFIX", "floxbot")

# Redis (entitlement cache)
REDIS_URL = os.environ.get("FLOXBOT_REDIS_URL", "redis://localhost:6379/0")
ENTITLEMENT_CACHE_TTL = int(os.environ.get("FLOXBOT_ENTITLEMENT_CACHE_TTL", "3600"))

# Database
DATABASE_URL = os.environ.get(
    "FLOXBOT_DATABASE_URL",
    "postgresql+asyncpg://floxbot:floxbot@localhost:5432/floxbot",
)

# Vector store (same DB, pgvector extension)
VECTOR_STORE_URL = os.environ.get(
    "FLOXBOT_VECTOR_STORE_URL",
    "postgresql+asyncpg://floxbot:floxbot@localhost:5432/floxbot",
)

# FloxHub auth
FLOXHUB_AUTH_DIR = Path(os.environ.get("FLOXHUB_AUTH_DIR", str(Path.home() / ".flox")))

# Canon / RAG
CANON_SOURCE_DIR = os.environ.get("FLOXBOT_CANON_SOURCE_DIR", "./skills")
CANON_CHUNK_SIZE = int(os.environ.get("FLOXBOT_CANON_CHUNK_SIZE", "512"))
CANON_CHUNK_OVERLAP = int(os.environ.get("FLOXBOT_CANON_CHUNK_OVERLAP", "64"))
RAG_TOP_K = int(os.environ.get("FLOXBOT_RAG_TOP_K", "5"))
RAG_SIMILARITY_THRESHOLD = float(os.environ.get("FLOXBOT_RAG_SIMILARITY_THRESHOLD", "0.3"))

# Skills
SKILLS_PATH = os.environ.get("FLOXBOT_SKILLS_PATH", "./skills")
MAX_SKILLS_PER_TURN = 2
PRIMARY_SKILL_TOKEN_BUDGET = 8000
SECONDARY_SKILL_TOKEN_BUDGET = 4000

# Escalation
ESCALATION_CONFIDENCE_THRESHOLD = float(os.environ.get("FLOXBOT_ESCALATION_THRESHOLD", "0.3"))
MAX_ESCALATION_ATTEMPTS = 3

# Dev mode
DEV_TOKEN = os.environ.get("FLOXBOT_DEV_TOKEN", "")
