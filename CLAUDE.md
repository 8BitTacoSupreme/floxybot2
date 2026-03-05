# CLAUDE.md — FloxBot Support System

## What This Project Is

FloxBot is a multi-channel, context-aware support system for Flox users. It handles L1/L2 technical support across Slack, Discord, email, CLI, and a local Co-Pilot — all backed by a shared Central API. The system dynamically loads skill packages based on user context, maintains persistent cross-channel memory, and feeds vote-labeled data upstream to continuously improve its knowledge base.

## Architecture Overview

Read `docs/architecture-v2.md` for the full spec. The diagrams are in `docs/diagrams/`. Here are the key pieces:

### The Brain (Central API)

- FastAPI (Python), lives in `support-bot-api/`
- Orchestrates: auth + entitlement gating → context engine → skill detection → intent router → LLM call → response
- Two LLM backends: **Claude** (conversation, reasoning, teaching, orchestration) and **Codex** (code generation, manifest editing, debugging)
- Both get the same context injection: user memory, RAG results, skill packages, project context, MCP tools
- Intent-based routing: CONVERSATIONAL → Claude, CODE_GENERATION → Codex, DIAGNOSTIC → Claude orchestrates + delegates to Codex, TEACHING → Claude co-pilot mode

### Channel Adapters

Thin, stateless. All normalize to the same message format and hit the Central API via sync HTTP.

- **Slack** — Node.js, Bolt SDK, Socket Mode. Lives in `support-bot-slack/`
- **Discord** — Node.js, discord.js, Gateway WebSocket. Lives in `support-bot-discord/`
- **Email** — Python, SendGrid inbound parse. Lives in `support-bot-email/`
- **CLI** — Python, lightweight (ask/chat only). Lives in `support-bot-cli/`
- **Co-Pilot** — Python, full-featured, local-first with sync. Lives in `support-bot-copilot/`

### Event Backbone

- **Kafka** — Async side effects ONLY. Never in the user-facing hot path. The user waits for a sync HTTP response, not a Kafka round-trip.
- **Topics:** `.inbound`, `.outbound`, `.votes`, `.context`, `.escalations`, `.feedback`, `.sessions.xc`, `.telemetry`, `.canon.updates`
- **Flink** — 4 streaming jobs: vote aggregation (tumbling 1h + sliding 24h), cross-channel session correlation (session window 30-min gap), canon gap detection (daily tumbling), trending issues (sliding 4h)
- Lives in `support-bot-kafka/` and `support-bot-flink/`

### Knowledge Architecture

Three tiers:
1. **Tier 1: User Memory** — Per-user, real-time. Projects, skill level, past issues, preferences.
2. **Tier 2: Instance Knowledge** — Org-level patterns, popular questions, community-voted best answers. Daily aggregation from votes.
3. **Tier 3: Upstream Canon** — Flox docs, SKILL.md corpus, curated Q&A, resolved tickets. Weekly export with human review gate.

### Skills as Packages

Each skill (k8s, terraform, aws, etc.) is a self-contained bundle published to FloxHub:

```
skill:k8s/
├── SKILL.md            # Primary knowledge doc
├── prompts/            # Diagnostic + pattern prompt fragments
├── examples/           # Annotated manifest examples
├── qa/                 # Curated Q&A pairs (from votes)
├── embeddings/         # Pre-computed vectors
└── metadata.json       # Triggers, version, deps, weight
```

Detection signals (ranked by confidence): manifest inspection > message content analysis > user memory > conversation history. Max 2 active skills per turn (context window budget). Primary skill gets full load (~8k tokens), secondary gets summary (~4k tokens).

### Co-Pilot

A standalone Flox environment for 1:1 learning and support. Six modes:
- **ask** — Single-shot Q&A (all tiers)
- **chat** — Multi-turn conversation (all tiers)
- **diagnose** — Environment analysis (all tiers)
- **learn** — Guided growth paths (Pro/Enterprise)
- **feedback** — Structured field intelligence (Pro/Enterprise)
- **ticket** — Bot-triaged support ticket with full context bundle (Pro/Enterprise)

Local-first: SQLite + ChromaDB for offline canon, JSONL queues for votes/feedback/tickets, syncs on activate or manual `copilot-sync`.

### Entitlement Model

Resolved via FloxHub auth, cached in Redis (1h TTL):
- **Community** (free) — L1 support, basic skills, votes, CLI ask/chat, rate limited
- **Pro** (paid) — L2 support, full skills, co-pilot learn/diagnose/feedback/ticket, Codex, full memory
- **Enterprise** (org) — Org-wide knowledge, custom skills, SSO, admin dashboard, SLA

### Cross-Channel Awareness

Confidence-tiered surfacing:
- **High** (>0.85 similarity, <24h) — Explicitly mention ("I see you were working on this in Slack")
- **Medium** (0.60-0.85, <72h) — Ask gently ("Is this the same project?")
- **Low** (0.40-0.60, any time) — Use silently to improve response quality
- **Never** — Unlinked accounts, private DMs in public channels

Cross-channel surfacing only in DMs/private contexts. In public channels, use context silently or not at all.

## Project Structure

```
floxbot/
├── CLAUDE.md                        # You are here
├── docs/
│   ├── architecture-v2.md           # Full architecture spec
│   └── diagrams/                    # Mermaid diagrams (01-11)
│
├── support-bot-api/                 # Central API (Python/FastAPI)
│   ├── .flox/env/manifest.toml
│   └── src/
│       ├── main.py                  # FastAPI app
│       ├── auth/                    # FloxHub auth + entitlement resolution
│       ├── context/                 # Context engine, skill detection
│       ├── router/                  # Intent classification, LLM routing
│       ├── llm/                     # Claude + Codex backends
│       ├── rag/                     # Canon + RAG engine
│       ├── memory/                  # User memory (Tier 1)
│       ├── skills/                  # Skill package loading + budget mgmt
│       ├── escalation/              # Intercom bridge
│       └── models/                  # Shared types, normalized message schema
│
├── support-bot-slack/               # Slack adapter (Node.js/Bolt)
│   ├── .flox/env/manifest.toml
│   └── src/
│
├── support-bot-discord/             # Discord adapter (Node.js/discord.js)
│   ├── .flox/env/manifest.toml
│   └── src/
│
├── support-bot-email/               # Email adapter (Python/SendGrid)
│   ├── .flox/env/manifest.toml
│   └── src/
│
├── support-bot-cli/                 # CLI (Python, lightweight)
│   ├── .flox/env/manifest.toml
│   └── src/
│
├── support-bot-copilot/             # Co-Pilot (Python, full-featured)
│   ├── .flox/env/manifest.toml
│   └── src/
│       ├── copilot.py               # Main entry point
│       ├── modes/                   # ask, chat, diagnose, learn, feedback, ticket
│       ├── sync.py                  # Canon + memory + queue sync
│       └── local/                   # SQLite + ChromaDB local stores
│
├── support-bot-canon/               # Canon forge (build/test knowledge)
│   ├── .flox/env/manifest.toml
│   └── scripts/
│       ├── index_canon.py           # Embedding pipeline
│       ├── eval_harness.py          # Q&A eval against ground truth
│       └── export_upstream.py       # Anonymized weekly export
│
├── support-bot-kafka/               # Kafka + Zookeeper
│   ├── .flox/env/manifest.toml
│   └── config/
│
├── support-bot-flink/               # Flink jobs
│   ├── .flox/env/manifest.toml
│   └── jobs/
│       ├── vote_aggregation.py
│       ├── cross_channel_correlation.py
│       ├── canon_gap_detection.py
│       └── trending_issues.py
│
├── support-bot-shared/              # Shared types, MCP server, configs
│   ├── .flox/env/manifest.toml
│   └── src/
│       ├── mcp_server/              # Flox MCP server (flox search/show/validate)
│       ├── schemas/                 # Normalized message, vote, feedback schemas
│       └── config/                  # Shared configuration
│
└── skills/                          # Skill packages (published to FloxHub)
    ├── core-canon/
    ├── skill-k8s/
    ├── skill-terraform/
    ├── skill-aws/
    ├── skill-gcp/
    ├── skill-docker/
    ├── skill-postgres/
    ├── skill-rust/
    └── skill-python/
```

## Flox Environment Conventions

Every component has its own `.flox/env/manifest.toml`. Follow these rules:

- **Never use absolute paths.** Use `$FLOX_ENV`, `$FLOX_ENV_PROJECT`, `$FLOX_ENV_CACHE`.
- **Persistent data** goes in `$FLOX_ENV_CACHE` (survives `flox delete`).
- **Hooks must be idempotent.** They run every activation. Guard with flag files.
- **Use `return` not `exit`** in hooks.
- **Default env vars** with `${VAR:-default}` pattern.
- **Namespace everything** in composable environments: prefix vars, functions, services with `floxbot_`.
- **Secrets never go in manifests.** Use env vars or `~/.config/<env>/`.
- **Shared dependencies** go in `support-bot-shared/` and are composed via `[include]`.
- **Test activation** with `flox activate -- <command>` before adding to services.

## Normalized Message Schema

Every adapter normalizes to this format before hitting the Central API:

```json
{
  "message_id": "uuid",
  "user_identity": {
    "channel": "slack|discord|email|cli|copilot",
    "channel_user_id": "...",
    "email": "...",
    "canonical_user_id": "usr_...",
    "floxhub_username": "...",
    "entitlement_tier": "community|pro|enterprise"
  },
  "content": {
    "text": "...",
    "attachments": [],
    "code_blocks": []
  },
  "context": {
    "project": {
      "has_flox_env": true,
      "manifest": "...",
      "detected_skills": ["terraform", "aws"]
    },
    "conversation_id": "conv_...",
    "channel_metadata": {}
  },
  "session": {
    "prior_messages": 0,
    "active_skills": [],
    "escalation_attempts": 0,
    "copilot_active": false
  }
}
```

## Key Technical Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Hot path | Sync HTTP, not Kafka | User is waiting. Latency matters. |
| Kafka | Async side effects only | Decoupling, replay, fan-out, audit |
| Vector store | pgvector → Qdrant at scale | pgvector ships in Flox easily |
| LLM routing | Intent-based | Claude for conversation, Codex for code |
| Skill budget | Max 2 per turn | Context window is finite |
| Identity | FloxHub username primary | Strongest cross-channel link |
| Cross-channel | Confidence-tiered | High=mention, medium=ask, low=silent |
| Co-pilot offline | SQLite + ChromaDB + JSONL queues | Must work on planes |
| Entitlements | Redis-cached, FloxHub-resolved | Fast lookup, single source of truth |

## Build Order

1. **Foundation** — Central API, canon pipeline, RAG, CLI adapter, FloxHub auth, vote store
2. **Co-Pilot + Entitlements** — Co-pilot env, entitlement gate, local canon sync, offline queuing
3. **Multi-Channel** — Slack, Discord, email adapters, cross-channel identity, Intercom bridge
4. **Intelligence** — Codex integration, skill detection + loading, user memory, instance knowledge, MCP server
5. **Streaming + Feedback** — Kafka, Flink jobs, field feedback pipeline, triaged tickets, learn mode
6. **Enterprise** — Org knowledge, custom skills, SSO, admin dashboard, SLA routing, telemetry

## Code Style and Conventions

- **Python:** Type hints everywhere. Pydantic models for all schemas. Async where appropriate (FastAPI).
- **Node.js:** TypeScript for adapters. Strict mode.
- **Error handling:** Never swallow errors silently. Log with context. Degrade gracefully.
- **Testing:** Every skill package has an eval harness. API endpoints have integration tests. Adapters have contract tests against the normalized message schema.
- **Manifests:** Always validate with `flox edit` before committing. Test activation with `flox activate -- <command>`.

## MCP Server

The Flox MCP server (`support-bot-shared/src/mcp_server/`) exposes:
- `flox_search` — Search the Flox catalog
- `flox_show` — Show package versions
- `flox_validate_manifest` — Validate a manifest.toml
- `flox_list_remote` — List packages in a remote environment
- `floxhub_env_metadata` — Get environment metadata from FloxHub

Both Claude and Codex backends have access to these tools.

## Escalation Rules

- **L1** (target 80%) — RAG + skill Q&A, no human needed
- **L2** (target 15%) — Multi-turn, MCP tools, skill packages, user memory
- **Escalate** (<5%) — Auto-ticket on: explicit request, 3+ failed attempts on same topic, confidence < threshold, billing/account/security topics
- Entitled users get triaged tickets with full context bundles. Community users get basic Intercom tickets.

## What Not To Do

- Don't put Kafka in the hot path. The user-facing request/response is sync HTTP.
- Don't surface cross-channel context in public channels. DMs/private only.
- Don't load more than 2 skill packages per turn. Context budget is real.
- Don't store secrets in manifests. Ever.
- Don't use absolute paths in Flox environments.
- Don't skip the entitlement check. Every request goes through the gate.
- Don't create Intercom tickets without the full context bundle (for entitled users).
- Don't send user code or project-specific data upstream without anonymization.
