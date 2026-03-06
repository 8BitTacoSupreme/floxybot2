# FloxBot Changelog

## Phase 3 — Canon Hydration, Multi-Channel, MCP Tools (2026-03-06)

### Completed
- **Embedder fix:** `rag/engine.py` now uses `voyageai.Client` directly instead of fragile `scripts.embedder` import
- **Canon pipeline:** `ingest_docs.py` multi-source ingestion, `scrape_flox_docs.py` scraper, extended chunker
- **RAG boosting:** Source-type weighted scoring (LRM pattern) — flox_docs > blog_posts > nix_docs
- **Labeled prompts:** System prompt includes source labels for grounded responses
- **MCP tool registry:** `flox_search`, `flox_show`, `flox_validate_manifest`, `flox_list_remote`, `floxhub_env_metadata`
- **Tool-use loop:** Multi-step LLM interactions with tool calls
- **Slack adapter:** Bolt SDK, Socket Mode, normalizer + formatter with code block extraction
- **Discord adapter:** discord.js, Gateway WebSocket, normalizer + formatter with guild/thread support
- **Email adapter:** SendGrid inbound parse webhook, email normalizer, HTML reply formatter
- **Cross-channel identity:** `ChannelIdentity` model linking users across channels
- **Adapter contract tests:** Schema compliance validation for all adapter normalizer outputs
- **Namespace fix:** `pkgutil.extend_path` in all `src/__init__.py` for cross-component imports
- **245 tests passing** (32 new)

### Known Gaps
- Skill packages (`skills/`) are empty stubs — no SKILL.md content, no embeddings
- Kafka/Flink streaming not started (Phase 5)
- Codex integration not started (Phase 4)
- Skill detection + loading not started (Phase 4)
- User memory (Tier 1) not started (Phase 4)
- No CI/CD pipeline yet
- Canon hydration requires manual run with `VOYAGE_API_KEY` and PostgreSQL (Task C4)

---

## Phase 2 — Co-Pilot + Entitlements (2026-03-06)

### Completed
- **Co-Pilot:** Standalone entry point with 6 modes (ask, chat, diagnose, learn, feedback, ticket)
- **Local-first architecture:** SQLite for memory, ChromaDB for local canon, JSONL queues for offline ops
- **Entitlement gating:** Tier-based mode access (community → ask/chat, pro → all modes)
- **Rate limiter:** Sliding window per-user limits with Redis backing
- **Ticket system:** Auto-priority assignment, context bundle generation
- **Canon sync:** Local canon + memory sync on activate, queue flush
- **72 new tests** covering all co-pilot modes and entitlements

---

## Phase 1 — Foundation (2026-03-05)

### Completed
- Central API (FastAPI) with `/v1/message`, `/v1/vote`, `/v1/feedback` endpoints
- Claude LLM backend with system prompts
- RAG engine with pgvector cosine similarity search
- Canon pipeline: chunker + indexer for SKILL.md files
- CLI adapter (ask/chat modes)
- FloxHub auth with dev token support
- Vote recording and feedback collection
- PostgreSQL + pgvector schema with alembic migrations
- Normalized message schema (Pydantic)
- 141 tests passing
