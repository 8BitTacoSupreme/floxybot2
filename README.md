# FloxBot

Multi-channel, context-aware support system for [Flox](https://flox.dev) users. Handles L1/L2 technical support across Slack, Discord, email, CLI, and a local-first Co-Pilot — all backed by a shared Central API.

```
Channels          Central API (The Brain)              Data Layer
─────────         ──────────────────────────           ──────────
Slack ──┐         Auth + Entitlement Gate              PostgreSQL + pgvector
Discord ─┼─ HTTP ─→ Context Engine                     Redis (cache, rate limits)
Email ──┤         Skill Detection (max 2/turn)         Kafka (async side effects)
CLI ────┤         Intent Router                        Flink (stream processing)
Co-Pilot┘         Claude / Codex LLM backends
```

## Quick Start

### Prerequisites

- **Python 3.13+**
- **PostgreSQL 16** with the `pgvector` extension
- Python packages: `pip install -r requirements.txt` (or activate the Flox environment)

Optional (graceful degradation without):
- Redis (entitlement caching, rate limits)
- Kafka (async event publishing)
- Anthropic API key (LLM calls)
- Voyage API key (embeddings)

### Database Setup

```bash
# Create the databases
createdb floxbot
createdb floxbot_test

# Create the user
psql -c "CREATE USER floxbot WITH PASSWORD 'floxbot';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE floxbot TO floxbot;"
psql -c "GRANT ALL PRIVILEGES ON DATABASE floxbot_test TO floxbot;"

# Enable pgvector (run in each database)
psql -d floxbot -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -d floxbot_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Run the Tests

```bash
PYTHONPATH=support-bot-copilot:support-bot-api:support-bot-shared:support-bot-email:support-bot-canon:support-bot-cli:support-bot-flink:support-bot-kafka \
  python3 -m pytest tests/ -q
```

No external services needed beyond PostgreSQL. Tests mock Redis (`fakeredis`), Kafka (`InMemoryPublisher`), and LLM APIs.

**Current status: 427 tests passing.**

### Run the API Server

```bash
export ANTHROPIC_API_KEY="sk-..."   # Required for LLM calls
export VOYAGE_API_KEY="..."         # Required for embeddings

cd support-bot-api
PYTHONPATH=../support-bot-shared uvicorn src.main:app --reload --port 8000
```

The API degrades gracefully — no Redis means no entitlement caching, no Kafka means events stay in-memory, no Intercom key means escalation returns stubs.

### Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Architecture

### Hot Path (Sync HTTP)

Every user-facing request follows the same pipeline. The user waits for a sync HTTP response — Kafka is never in the hot path.

```
Message → Auth → Rate Limit → Context Engine → Skill Detection → Intent Classification → LLM → Response
```

### Dual LLM Backends

| Intent | Backend | Use Case |
|--------|---------|----------|
| `CONVERSATIONAL` | Claude | Q&A, explanations, general support |
| `CODE_GENERATION` | Codex | Manifest editing, code fixes, scaffolding |
| `DIAGNOSTIC` | Claude + Codex | Claude orchestrates, delegates code tasks to Codex |
| `TEACHING` | Claude | Guided learning, co-pilot learn mode |

### Three-Tier Knowledge

| Tier | Scope | Refresh | Store |
|------|-------|---------|-------|
| **Tier 1: User Memory** | Per-user | Real-time | PostgreSQL |
| **Tier 2: Instance Knowledge** | Org / global | Daily aggregation from votes | PostgreSQL |
| **Tier 3: Upstream Canon** | Global | Weekly export with human review gate | pgvector |

### Skills as Packages

Each skill is a self-contained bundle with detection triggers, knowledge docs, diagnostic prompts, and Q&A pairs. Max 2 skills loaded per turn (context window budget: primary 8k tokens, secondary 4k tokens).

```
skills/
├── core-canon/          # Flox fundamentals (always available)
├── skill-aws/
├── skill-docker/
├── skill-gcp/
├── skill-k8s/
├── skill-postgres/
├── skill-python/
├── skill-rust/
└── skill-terraform/
```

Detection signals (ranked by confidence): manifest inspection > project context > message keywords > user memory.

### Entitlement Tiers

| | Community (free) | Pro (paid) | Enterprise (org) |
|---|---|---|---|
| Support level | L1 | L2 | L2 + SLA |
| Skills | Basic | Full | Full + custom |
| Co-Pilot modes | ask, chat | All 6 modes | All 6 modes |
| Codex | No | Yes | Yes |
| User memory | No | Yes | Yes |
| Org knowledge | No | No | Yes |
| Admin dashboard | No | No | Yes |
| Rate limit | 10 rpm | 60 rpm | 120 rpm |

### Event Backbone

Kafka handles async side effects only — never in the user-facing hot path.

**Topics:** `.inbound`, `.outbound`, `.votes`, `.context`, `.escalations`, `.feedback`, `.sessions.xc`, `.telemetry`, `.canon.updates`

**Flink Jobs:**
- Vote aggregation (tumbling 1h + sliding 24h)
- Cross-channel session correlation (session window, 30-min gap)
- Canon gap detection (daily tumbling)
- Trending issues (sliding 4h)
- Feedback routing (per-category classification)
- Telemetry aggregation (tumbling 1h, per-mode/skill/duration)

## Project Structure

```
floxybot/
├── support-bot-api/          # Central API (Python/FastAPI)
│   └── src/
│       ├── main.py           # FastAPI app, all endpoints
│       ├── auth/             # FloxHub auth + entitlement resolution
│       ├── context/          # Context engine
│       ├── router/           # Intent classification, LLM routing
│       ├── llm/              # Claude + Codex backends
│       ├── rag/              # Canon + RAG + instance knowledge
│       ├── memory/           # User memory, conversations, votes
│       ├── skills/           # Skill detection + loading
│       ├── escalation/       # Intercom bridge + SLA priority
│       ├── admin/            # Org stats + members (enterprise)
│       ├── events/           # Kafka publisher + sanitizer
│       └── db/               # SQLAlchemy models + engine
│
├── support-bot-slack/        # Slack adapter (Node.js/Bolt)
├── support-bot-discord/      # Discord adapter (Node.js/discord.js)
├── support-bot-email/        # Email adapter (Python/SendGrid)
├── support-bot-cli/          # CLI adapter (Python, lightweight)
├── support-bot-copilot/      # Co-Pilot (Python, local-first)
│   └── src/
│       ├── modes/            # ask, chat, diagnose, learn, feedback, ticket
│       ├── sync.py           # Canon + memory + queue + telemetry sync
│       └── local/            # SQLite + ChromaDB + JSONL queues
│
├── support-bot-canon/        # Canon forge
│   └── scripts/
│       ├── index_canon.py    # Embedding pipeline
│       ├── eval_harness.py   # Q&A eval against ground truth
│       └── export_upstream.py # Anonymized weekly export
│
├── support-bot-kafka/        # Kafka + Zookeeper config
├── support-bot-flink/        # Streaming consumers
│   ├── consumer_base.py      # Abstract StreamConsumer
│   ├── windows.py            # Tumbling, sliding, session windows
│   ├── runner.py             # CLI entry point
│   └── jobs/                 # 6 consumer implementations
│
├── support-bot-shared/       # Shared types, MCP server, config
├── skills/                   # Skill packages (9 skills)
├── tests/                    # 427 tests
└── docs/
    ├── architecture-v2.md    # Full architecture spec
    └── diagrams/             # 11 Mermaid diagrams
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/v1/message` | Main message endpoint (all adapters) |
| `POST` | `/v1/vote` | Record a vote |
| `POST` | `/v1/feedback` | Record structured feedback |
| `POST` | `/v1/votes/batch` | Batch vote upload (co-pilot sync) |
| `POST` | `/v1/tickets` | Create a triaged support ticket |
| `POST` | `/v1/telemetry` | Batch telemetry upload (co-pilot sync) |
| `GET` | `/v1/canon/sync` | Delta canon sync for co-pilot |
| `GET` | `/v1/memory/{user_id}` | Fetch user memory |
| `PUT` | `/v1/memory/{user_id}` | Update user memory |
| `GET` | `/v1/entitlements` | Resolve entitlements for auth header |
| `GET` | `/v1/admin/org/{org_id}/stats` | Org usage stats (enterprise) |
| `GET` | `/v1/admin/org/{org_id}/members` | Org member list (enterprise) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `VOYAGE_API_KEY` | — | Voyage embeddings API key |
| `FLOXBOT_DATABASE_URL` | `postgresql+asyncpg://floxbot:floxbot@localhost:5432/floxbot` | Database URL |
| `FLOXBOT_REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `FLOXBOT_KAFKA_BOOTSTRAP` | `localhost:9092` | Kafka bootstrap servers |
| `FLOXBOT_SKILLS_PATH` | `./skills` | Path to skill packages |
| `FLOXBOT_CUSTOM_SKILLS_PATH` | `./custom-skills` | Path to enterprise custom skills |
| `FLOXBOT_TIER_OVERRIDE` | — | Force a tier (dev/test: `community`, `pro`, `enterprise`) |
| `FLOXBOT_INTERCOM_API_KEY` | — | Intercom API key for escalation |

## Build Phases

All six phases are complete:

1. **Foundation** — Central API, canon pipeline, RAG, CLI adapter, FloxHub auth, vote store
2. **Co-Pilot + Entitlements** — Co-pilot with 6 modes, entitlement gating, rate limiting, local-first sync
3. **Multi-Channel** — Canon hydration, LRM boosting, MCP tools, Slack/Discord/email adapters
4. **Intelligence** — Codex backend, skill packages, intent scoring, user memory
5. **Streaming + Feedback** — Kafka event backbone, Flink consumers, Intercom bridge, feedback routing
6. **Enterprise** — Org model, custom skills, SLA routing, admin API, telemetry, canon eval/export

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Hot path | Sync HTTP | User is waiting. Latency matters. |
| Kafka | Async side effects only | Decoupling, replay, fan-out, audit |
| LLM routing | Intent-based | Claude for conversation, Codex for code |
| Skill budget | Max 2 per turn | Context window is finite |
| Cross-channel | Confidence-tiered | High: mention, Medium: ask, Low: silent |
| Co-pilot offline | SQLite + ChromaDB + JSONL | Must work on planes |
| Entitlements | Redis-cached, FloxHub-resolved | Fast lookup, single source of truth |

## Documentation

- **Architecture spec:** [`docs/architecture-v2.md`](docs/architecture-v2.md)
- **Diagrams:** [`docs/diagrams/`](docs/diagrams/) (11 Mermaid diagrams covering system overview, request flow, knowledge tiers, co-pilot, skills, entitlements, Kafka/Flink, cross-channel, escalation, build order, and environment topology)
- **Project instructions:** [`CLAUDE.md`](CLAUDE.md)
