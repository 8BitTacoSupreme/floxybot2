# Flox Support Bot — System Architecture v2

## Executive Summary

A multi-channel, context-aware support system that handles L1/L2 support for Flox users across CLI, Slack, Discord, and email. The system uses dual LLM backends (Claude + Codex), dynamically loads skill packages based on user context, maintains per-user memory with upstream feedback loops, and runs its own infrastructure inside Flox environments.

At its most ambitious, the system includes a standalone **Flox Co-Pilot** — a personal, local-first environment that serves as both a learning companion and a direct line into the support infrastructure. Entitlement tiers, gated by FloxHub auth, determine what each user can access: from community-level L1 support through to entitled users who can launch triaged tickets, submit structured field feedback, and maintain persistent co-pilot memory across sessions.

All infrastructure is Flox-managed, composable, and reproducible.

---

## Table of Contents

1. [Core Tensions and Resolutions](#1-core-tensions-and-resolutions)
2. [System Architecture](#2-system-architecture)
3. [Skills as Packages](#3-skills-as-packages)
4. [Channel Interaction Mechanics](#4-channel-interaction-mechanics)
5. [Claude + Codex Dual Residency](#5-claude--codex-dual-residency)
6. [L1 / L2 Support Tiers](#6-l1--l2-support-tiers)
7. [The Flox Co-Pilot](#7-the-flox-co-pilot)
8. [Entitlement Model](#8-entitlement-model)
9. [Feedback Loop Architecture](#9-feedback-loop-architecture)
10. [Cross-Channel Identity and Awareness](#10-cross-channel-identity-and-awareness)
11. [Kafka and Flink: The Event Backbone](#11-kafka-and-flink-the-event-backbone)
12. [Canon Management](#12-canon-management)
13. [Flox Environment Topology](#13-flox-environment-topology)
14. [Build Order](#14-build-order)
15. [Decision Log](#15-decision-log)

---

## 1. Core Tensions and Resolutions

### Tension 1: Transitive Knowledge

The bot needs to get smarter about *individual users* over time, while also contributing to *collective intelligence* upstream.

**Resolution: Three-tier knowledge architecture.**

```
┌─────────────────────────────────────────────────────────┐
│  Tier 3: Upstream Canon (slow, curated)                 │
│  - Anonymized vote aggregates                           │
│  - Curated Q&A pairs from high-confidence interactions  │
│  - Periodic fine-tuning datasets                        │
│  - Flox docs, SKILL.md corpus, release notes            │
│  Refresh: Weekly export → human review → canon merge    │
├─────────────────────────────────────────────────────────┤
│  Tier 2: Instance Knowledge (medium, automated)         │
│  - Org-level patterns ("users keep hitting X error")    │
│  - Popular questions / trending issues                  │
│  - Community-voted best answers                         │
│  Refresh: Daily aggregation from vote store             │
├─────────────────────────────────────────────────────────┤
│  Tier 1: User Memory (fast, per-user)                   │
│  - Projects they work on, manifest patterns             │
│  - Skill level (beginner → advanced)                    │
│  - Past issues and resolutions                          │
│  - Communication preferences                            │
│  Refresh: Real-time, every interaction                  │
└─────────────────────────────────────────────────────────┘
```

**Vote flow:**
1. User votes response up/down in any channel
2. Vote stored with: `(user_id, query, response, context_snapshot, channel, vote, timestamp)`
3. High-voted responses → candidate for Tier 2 (instance knowledge)
4. Curated Tier 2 entries → exported upstream to Tier 3 (with user consent)
5. Tier 3 periodically reprocessed into updated RAG embeddings + fine-tuning data

The key insight: **votes are not just feedback, they're labeled training data.** A downvote on a response about `flox services` tells you the canon for services needs improvement. An upvote on a creative workaround means the workaround should be canonized.

### Tension 2: Self-Containment vs Phone Home

Slack, Discord, email, and CLI all need the same brain. But the CLI and Co-Pilot also need to work offline or at least degrade gracefully.

**Resolution: Shared backend API + local-first modes with sync.**

```
                    ┌──────────────────────┐
                    │   FloxBot Central    │
                    │   API (the brain)    │
                    │                      │
                    │  • LLM orchestration │
                    │  • RAG/Canon engine  │
                    │  • User memory store │
                    │  • Vote aggregation  │
                    │  • Entitlement gate  │
                    │  • Intercom bridge   │
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                     │
   ┌──────┴──────┐   ┌────────┴──────┐    ┌────────┴──────┐
   │ Slack Bot   │   │ Discord Bot   │    │ Email Bot     │
   │ (adapter)   │   │ (adapter)     │    │ (adapter)     │
   └─────────────┘   └───────────────┘    └───────────────┘

   ┌──────────────────────────────────────────────────────┐
   │  CLI / Co-Pilot (local-first)                        │
   │                                                      │
   │  Online:    → hits Central API (full capability)     │
   │  Offline:   → local canon + local model (degraded)   │
   │  Reconnect: → sync votes, memory, canon updates      │
   └──────────────────────────────────────────────────────┘
```

Each channel adapter is thin — it handles platform-specific I/O and passes everything else to the Central API. The adapters don't hold state. The CLI/Co-Pilot is the exception: it maintains a local canon cache and can operate independently, syncing when connectivity returns.

---

## 2. System Architecture

### Layer 1: Channel Adapters

```
┌─────────────────────────────────────────────────────────────┐
│                     Channel Adapters                         │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │  Slack   │  │ Discord  │  │  Email   │  │ CLI /      │  │
│  │          │  │          │  │          │  │ Co-Pilot   │  │
│  │ Socket   │  │ Gateway  │  │ Webhook/ │  │            │  │
│  │ Mode /   │  │ + slash  │  │ IMAP     │  │ stdin/out  │  │
│  │ Events   │  │ commands │  │ polling  │  │ + MCP      │  │
│  │ API      │  │          │  │          │  │ + FloxHub  │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬─────┘  │
│       │              │              │               │        │
│       └──────────────┴──────┬───────┴───────────────┘        │
│                             │                                │
│                    Normalized Message                         │
│                    {                                          │
│                      user_id,                                 │
│                      channel: "slack"|"discord"|"email"|      │
│                              "cli"|"copilot",                 │
│                      channel_context: {...},                   │
│                      message,                                 │
│                      attachments: [],                          │
│                      project_context?: {...},                  │
│                      entitlement_tier: "community"|            │
│                                       "pro"|"enterprise"      │
│                    }                                          │
└─────────────────────────────┬────────────────────────────────┘
                              ▼
```

**CLI/Co-Pilot affordance:** The local adapter can inspect the filesystem — detect `.flox/` directories, read `manifest.toml`, check `env.json` — and inject `project_context` into the normalized message. This is what makes it context-aware. The Slack/Discord bots can get equivalent context if the user shares a manifest snippet or links to a FloxHub environment.

### Layer 2: Central API (The Brain)

```
┌─────────────────────────────────────────────────────────────┐
│                    FloxBot Central API                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Auth + Entitlement Gate                             │   │
│  │                                                      │   │
│  │  1. Validate FloxHub token (or channel identity)     │   │
│  │  2. Resolve entitlement tier                         │   │
│  │  3. Apply rate limits + feature gates                │   │
│  └──────────────────────────┬───────────────────────────┘   │
│                             │                                │
│  ┌──────────────────────────▼───────────────────────────┐   │
│  │  Context Engine                                      │   │
│  │                                                      │   │
│  │  1. Identify user (cross-channel identity mapping)   │   │
│  │  2. Load user memory (Tier 1)                        │   │
│  │  3. Detect project context (.flox presence, etc)     │   │
│  │  4. Detect + load relevant skill packages            │   │
│  │  5. Classify intent + urgency                        │   │
│  │  6. Determine support tier (L1 / L2 / escalate)     │   │
│  │  7. Check cross-channel session (Flink output)       │   │
│  └──────────────────────────┬───────────────────────────┘   │
│                             │                                │
│  ┌──────────────────────────▼───────────────────────────┐   │
│  │  Router / Orchestrator                               │   │
│  │                                                      │   │
│  │  Intent-based routing:                               │   │
│  │  ┌─────────────────┬────────────────────────────┐    │   │
│  │  │ "How do I..."   │ → Claude (conversational)  │    │   │
│  │  │ "Fix my manif." │ → Codex (code gen/edit)    │    │   │
│  │  │ "Write a hook"  │ → Codex (code gen)         │    │   │
│  │  │ "Explain error" │ → Claude (diagnostic)      │    │   │
│  │  │ "Debug my env"  │ → Codex + MCP (inspect)    │    │   │
│  │  │ "Teach me..."   │ → Claude (co-pilot mode)   │    │   │
│  │  │ Complex / mixed │ → Claude orchestrates,     │    │   │
│  │  │                 │   delegates to Codex        │    │   │
│  │  └─────────────────┴────────────────────────────┘    │   │
│  └──────────────────────────┬───────────────────────────┘   │
│                             │                                │
│  ┌──────────────────────────▼───────────────────────────┐   │
│  │  LLM Backends                                        │   │
│  │                                                      │   │
│  │  ┌────────────────────┐  ┌────────────────────┐      │   │
│  │  │ Claude             │  │ Codex              │      │   │
│  │  │                    │  │                    │      │   │
│  │  │ System prompt:     │  │ System prompt:     │      │   │
│  │  │ - Flox SKILLS      │  │ - Flox SKILLS      │      │   │
│  │  │ - User memory      │  │ - User memory      │      │   │
│  │  │ - RAG context      │  │ - RAG context      │      │   │
│  │  │ - Skill packages   │  │ - Skill packages   │      │   │
│  │  │ - MCP tools        │  │ - Project files    │      │   │
│  │  │                    │  │ - MCP tools        │      │   │
│  │  │ Strengths:         │  │                    │      │   │
│  │  │ - Conversation     │  │ Strengths:         │      │   │
│  │  │ - Reasoning        │  │ - Code generation  │      │   │
│  │  │ - Explanation      │  │ - Manifest editing │      │   │
│  │  │ - Teaching         │  │ - Debugging        │      │   │
│  │  │ - Nuanced support  │  │ - Refactoring      │      │   │
│  │  └────────────────────┘  └────────────────────┘      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Canon + RAG Engine                                  │   │
│  │                                                      │   │
│  │  Vector Store (pgvector → Qdrant at scale):          │   │
│  │  - Flox documentation (chunked + embedded)           │   │
│  │  - SKILL.md corpus (all skills)                      │   │
│  │  - Skill packages (dynamically loaded)               │   │
│  │  - Curated Q&A pairs (from Tier 2/3)                 │   │
│  │  - Release notes + changelogs                        │   │
│  │  - GitHub issues / discussions (relevant)             │   │
│  │  - Intercom resolved tickets                         │   │
│  │                                                      │   │
│  │  MCP Server:                                         │   │
│  │  - flox search / flox show (live catalog queries)    │   │
│  │  - flox list (inspect remote environments)           │   │
│  │  - Manifest validation                               │   │
│  │  - FloxHub API (environment metadata)                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Feedback + Escalation                               │   │
│  │                                                      │   │
│  │  Vote Store:                                         │   │
│  │  - All votes with full context snapshots             │   │
│  │  - Aggregation pipeline (daily)                      │   │
│  │  - Export pipeline (weekly, anonymized, upstream)     │   │
│  │                                                      │   │
│  │  Intercom Bridge:                                    │   │
│  │  - Auto-create ticket on: explicit escalation req,   │   │
│  │    3+ failed attempts on same topic,                 │   │
│  │    low confidence score, or user frustration signal  │   │
│  │  - Ticket includes: full conversation, context,      │   │
│  │    project state, attempted resolutions              │   │
│  │  - Entitled users: structured ticket with triage     │   │
│  │  - Community users: basic ticket, lower priority     │   │
│  │                                                      │   │
│  │  Escalation triggers:                                │   │
│  │  - Confidence < threshold                            │   │
│  │  - "talk to a human" / "open a ticket"               │   │
│  │  - Repeated downvotes in same session                │   │
│  │  - Topic classified as billing/account/security      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Layer 3: Data Stores

```
┌─────────────────────────────────────────────────────────────┐
│  Data Layer                                                 │
│                                                             │
│  ┌─────────────────────┐  ┌─────────────────────────────┐   │
│  │ PostgreSQL           │  │ Vector Store                │   │
│  │                      │  │ (pgvector or Qdrant)        │   │
│  │ - User profiles      │  │                             │   │
│  │ - User memory        │  │ - Canon embeddings          │   │
│  │ - Entitlements       │  │ - Q&A embeddings            │   │
│  │ - Cross-channel      │  │ - Skill embeddings          │   │
│  │   identity map       │  │                             │   │
│  │ - Vote records       │  │                             │   │
│  │ - Session history    │  │                             │   │
│  │ - Escalation log     │  │                             │   │
│  │ - Co-pilot progress  │  │                             │   │
│  └─────────────────────┘  └─────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────┐  ┌─────────────────────────────┐   │
│  │ Redis                │  │ Object Storage (S3/R2)      │   │
│  │                      │  │                             │   │
│  │ - Session cache      │  │ - Canon source files        │   │
│  │ - Rate limiting      │  │ - Embedding snapshots       │   │
│  │ - Entitlement cache  │  │ - Upstream export bundles   │   │
│  │ - Real-time state    │  │ - Co-pilot state snapshots  │   │
│  └─────────────────────┘  └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Skills as Packages

The bot shouldn't just know about Flox — it should know about Flox *in the context of whatever the user is actually building*. A user running terraform inside a Flox environment needs the bot to understand both worlds simultaneously.

### Detection → Resolution → Injection

```
User's environment / message
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Skill Detection Engine                                  │
│                                                          │
│  Signal sources (ranked by confidence):                  │
│                                                          │
│  1. Manifest inspection (highest confidence)             │
│     .flox/env/manifest.toml contains:                    │
│     - kubectl, kubernetes-helm → skill:k8s               │
│     - terraform → skill:terraform                        │
│     - awscli2, aws-sam-cli → skill:aws                   │
│     - google-cloud-sdk → skill:gcp                       │
│     - docker, docker-compose → skill:docker              │
│     - postgresql → skill:postgres                        │
│     - rustc, cargo → skill:rust                          │
│                                                          │
│  2. Message content analysis (medium confidence)         │
│     "my terraform plan is failing" → skill:terraform     │
│     "k8s pod keeps crashing" → skill:k8s                 │
│     "ECS task definition" → skill:aws                    │
│                                                          │
│  3. User memory (supporting signal)                      │
│     "User primarily works with AWS + Terraform"          │
│     Used to break ties and pre-load likely skills        │
│                                                          │
│  4. Conversation history (accumulating signal)           │
│     Prior messages in session referenced k8s → keep      │
│     skill:k8s loaded for follow-up questions             │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Skill Package Registry                                  │
│                                                          │
│  Each skill package is a self-contained bundle:          │
│                                                          │
│  skill:k8s/                                              │
│  ├── SKILL.md            # Primary knowledge doc         │
│  ├── prompts/            # Specialized prompt fragments  │
│  │   ├── diagnostic.md   # "How to debug k8s + Flox"    │
│  │   └── patterns.md     # "Common k8s manifest combos" │
│  ├── examples/           # Annotated manifest examples   │
│  │   ├── k8s-dev.toml    # Dev environment for k8s      │
│  │   └── k8s-ci.toml     # CI pipeline for k8s + Flox   │
│  ├── qa/                 # Curated Q&A pairs             │
│  │   └── k8s-faq.json    # High-voted k8s questions      │
│  ├── embeddings/         # Pre-computed vectors          │
│  │   └── chunks.parquet  # For RAG injection             │
│  └── metadata.json       # Version, dependencies, etc    │
│                                                          │
│  metadata.json:                                          │
│  {                                                       │
│    "name": "k8s",                                        │
│    "version": "1.3.0",                                   │
│    "triggers": {                                         │
│      "packages": ["kubectl", "kubernetes-helm",          │
│                    "k9s", "kustomize", "skaffold"],      │
│      "keywords": ["kubernetes", "k8s", "pod", "kubectl", │
│                    "helm", "deployment", "ingress"],      │
│      "file_patterns": ["**/k8s/**", "**/*.yaml"]         │
│    },                                                    │
│    "dependencies": [],                                   │
│    "conflicts": [],                                      │
│    "weight_kb": 340                                      │
│  }                                                       │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Context Window Budget Manager                           │
│                                                          │
│  The LLM has finite context. Skills compete for space.   │
│                                                          │
│  Budget allocation (example, 128k context):              │
│                                                          │
│  ┌────────────────────────────────┐                      │
│  │ System prompt + Flox core     │  ~8k tokens           │
│  │ (always loaded)               │                       │
│  ├────────────────────────────────┤                      │
│  │ User memory                   │  ~2k tokens           │
│  ├────────────────────────────────┤                      │
│  │ RAG results (canon)           │  ~6k tokens           │
│  ├────────────────────────────────┤                      │
│  │ ★ Dynamic skill slots ★       │  ~12k tokens          │
│  │   Primary skill (full)        │   ~8k                 │
│  │   Secondary skill (summary)   │   ~4k                 │
│  ├────────────────────────────────┤                      │
│  │ Conversation history          │  ~8k tokens           │
│  ├────────────────────────────────┤                      │
│  │ Project context (manifest)    │  ~2k tokens           │
│  ├────────────────────────────────┤                      │
│  │ Co-pilot state (if active)    │  ~2k tokens           │
│  ├────────────────────────────────┤                      │
│  │ Response headroom             │  ~4k tokens           │
│  └────────────────────────────────┘                      │
│                                                          │
│  Rules:                                                  │
│  - Max 2 active skills per turn (context budget)         │
│  - Primary skill: full SKILL.md + relevant examples      │
│  - Secondary skill: summary + targeted Q&A only          │
│  - If user crosses domains ("deploy my Flox env to k8s   │
│    on AWS"), load k8s primary + aws secondary             │
│  - Skills unload when conversation topic shifts           │
│  - User memory persists "frequently used skills" to      │
│    enable predictive pre-loading                         │
└──────────────────────────────────────────────────────────┘
```

### Skills as Flox Environments

Skills-as-packages maps directly onto Flox's own composition model:

```toml
# Skill packages are Flox environments on FloxHub
# Version-pinned, composable, independently testable

# The bot's canon environment composes skill packages:
[include]
environments = [
    { remote = "floxbot/core-canon" },
    { remote = "floxbot/skill-k8s", version = "1.3.0" },
    { remote = "floxbot/skill-terraform", version = "2.1.0" },
    { remote = "floxbot/skill-aws", version = "1.8.0" }
]
```

This means:
- **Skills are versioned and pinnable** — updating terraform support can't break k8s support
- **Skills are independently testable** — run evals against skill:k8s in isolation
- **Skills are community-contributable** — advanced users could submit skill packages
- **The canon forge environment composes all skills** for embedding generation
- **Runtime loads only what's needed** per conversation

### Skill Lifecycle

```
Author skill → Test in canon forge → Publish to FloxHub
                                           │
                                           ▼
                              Bot detects user needs k8s
                                           │
                                           ▼
                              Load skill:k8s into context
                                           │
                                           ▼
                              User votes on responses
                                           │
                                           ▼
                              Votes feed back into skill Q&A
                                           │
                                           ▼
                              Skill maintainer reviews, updates
                                           │
                                           ▼
                              New version published → bots pick up
```

---

## 4. Channel Interaction Mechanics

Each platform has different bot identity models, permission scopes, and interaction patterns.

### Slack

**Identity:** Slack App (Bot User) — created via Slack API, gets a bot user token. Appears as a "member" in channels it's invited to, clearly marked as [APP].

**Interaction patterns:**

| Trigger | Behavior |
|---------|----------|
| @floxbot in channel | Reply in thread (keeps channels clean) |
| DM to floxbot | Direct conversation |
| /floxbot slash command | Ephemeral or public response |
| Workflow trigger | Automated support routing |

**Technical:** Bolt SDK (Node.js or Python), Socket Mode preferred (no public endpoint needed). Scopes: `chat:write`, `reactions:read`, `im:history`, `channels:history`, `users:read`.

**Voting:** Block Kit interactive buttons (not emoji reactions — buttons give structured callback data):

```
┌──────────────────────────────────────────┐
│ [response text]                          │
│                                          │
│ [✅ Helpful]  [❌ Not helpful]  [🎫 Escalate] │
└──────────────────────────────────────────┘
```

### Discord

**Identity:** Discord Bot Application — created via Developer Portal, joins servers via OAuth2 invite link. Tagged [BOT] in member list.

**Interaction patterns:**

| Trigger | Behavior |
|---------|----------|
| @FloxBot in channel | Reply (or thread) |
| DM to FloxBot | Direct conversation |
| /floxbot slash command | Interaction response |
| New post in #support forum | Auto-reply to thread |

**Technical:** Discord.js or discord.py, Gateway WebSocket (persistent connection). Needs MESSAGE_CONTENT and GUILD_MEMBERS privileged intents.

**Recommended:** Dedicated #flox-support forum channel where the bot auto-monitors new posts. Embeds for rich responses. Component buttons for voting.

### Email

**Identity:** support@flox.dev — processed via SendGrid Inbound Parse (webhook) or IMAP polling.

**Interaction patterns:**

| Trigger | Behavior |
|---------|----------|
| Email to support@ | Auto-reply with bot response |
| Reply to bot email | Continues conversation (via In-Reply-To headers) |
| "not helpful" reply | Downvote + potential escalation |

**Voting:** Footer links in every bot email hitting a webhook endpoint for structured vote capture.

### CLI

**Identity:** Local process, authenticated via FloxHub token (from `flox auth`) or API key.

**Interaction patterns:**

| Trigger | Behavior |
|---------|----------|
| `floxbot "question"` | Single-shot Q&A |
| `floxbot chat` | Interactive REPL mode |
| `floxbot --context` | Auto-inject manifest context |
| `floxbot diagnose` | Full env analysis + suggestions |
| y/n after response | Inline vote prompt |

### The Adapter Contract

Every adapter normalizes to the same message format:

```json
{
  "message_id": "uuid",
  "user_identity": {
    "channel": "slack",
    "channel_user_id": "U04ABCDEF",
    "email": "jeremy@flox.dev",
    "canonical_user_id": "usr_abc123",
    "floxhub_username": "jeremy",
    "entitlement_tier": "pro"
  },
  "content": {
    "text": "Why is my terraform plan failing inside flox activate?",
    "attachments": [],
    "code_blocks": []
  },
  "context": {
    "project": {
      "has_flox_env": true,
      "manifest": "...",
      "detected_skills": ["terraform", "aws"]
    },
    "conversation_id": "conv_xyz",
    "channel_metadata": {
      "slack_channel": "#infra-help",
      "is_thread": true,
      "thread_ts": "1234567890.123456"
    }
  },
  "session": {
    "prior_messages": 3,
    "active_skills": ["terraform"],
    "escalation_attempts": 0,
    "copilot_active": false
  }
}
```

The Central API returns a normalized response that each adapter renders in its native format.

---

## 5. Claude + Codex Dual Residency

Both models get the same context injection (user memory, RAG results, skill packages, project context). The router selects based on intent:

```
User query
    │
    ▼
┌──────────────────────────────────────────────┐
│  Intent Classifier (lightweight, fast)       │
│                                              │
│  Categories:                                 │
│  CONVERSATIONAL → Claude                     │
│    "how do I", "explain", "what is",         │
│    "should I", "compare", "recommend"        │
│                                              │
│  CODE_GENERATION → Codex                     │
│    "write a hook", "create manifest",        │
│    "fix this", "generate", "build script"    │
│                                              │
│  DIAGNOSTIC → Claude (orchestrator)          │
│    "why is my env broken", "debug this"      │
│    Claude reasons → may delegate code        │
│    analysis subtasks to Codex                │
│                                              │
│  TEACHING → Claude (co-pilot mode)           │
│    "teach me", "walk me through",            │
│    "I don't understand", learning paths      │
│                                              │
│  HYBRID → Claude primary, Codex secondary    │
│    "explain this error and fix it"           │
│    Claude explains, calls Codex for fix      │
│                                              │
│  ESCALATION → Intercom                       │
│    "talk to human", billing, account         │
└──────────────────────────────────────────────┘
```

Both models are equipped with the Flox MCP server, so they can execute `flox search`, `flox show`, validate manifests, and inspect environments in real-time.

---

## 6. L1 / L2 Support Tiers

### L1 — Instant Resolution (Target: 80% of queries)

- Direct doc/canon lookup ("how do I install a package?")
- Common error patterns with known fixes
- Manifest syntax questions
- Package search and version queries
- Getting-started guidance

Handled entirely by RAG + LLM, no human intervention.

### L2 — Contextual Problem-Solving (Target: 15% of queries)

- Environment debugging (requires reading user's manifest/context)
- Cross-platform issues (Darwin vs Linux package conflicts)
- Complex composition/layering questions
- Performance troubleshooting
- Integration questions (CI/CD, Docker interop)
- Skill-specific deep dives (k8s + Flox, terraform + Flox)

Handled by LLM with deeper reasoning, MCP tool use, skill packages, and user memory. May take multiple turns.

### Escalation to Human (Target: <5%)

- Novel bugs in Flox itself
- Account/billing issues
- Feature requests (captured, not resolved)
- Persistent unresolved issues (3+ failed attempts)
- Explicit user request

Auto-creates Intercom ticket with full context bundle:

```json
{
  "user_id": "...",
  "entitlement_tier": "pro",
  "channel": "slack",
  "conversation_history": [...],
  "project_context": {
    "manifest": "...",
    "env_json": "...",
    "flox_version": "..."
  },
  "active_skills": ["terraform", "aws"],
  "attempted_resolutions": [...],
  "classification": "novel_bug",
  "confidence_score": 0.23,
  "copilot_progress": { ... }
}
```

---

## 7. The Flox Co-Pilot

This is the most differentiated piece of the architecture. Not just a support bot — a **personal, context-aware development companion** that lives inside a Flox environment, learns the user over time, and connects back to the central infrastructure in meaningful ways.

### What Is It?

A standalone Flox environment that a user activates locally. It provides:

1. **A personal AI assistant** that understands their specific Flox setup, projects, and skill level
2. **Guided learning paths** — not just answering questions, but proactively teaching
3. **A direct line to support infrastructure** — triaged tickets, field feedback, canon contributions
4. **Persistent local state** that syncs upstream when connected

### The Co-Pilot Environment

```toml
# flox/copilot/.flox/env/manifest.toml

[install]
python.pkg-path = "python311Full"
uv.pkg-path = "uv"
sqlite.pkg-path = "sqlite"
jq.pkg-path = "jq"

[vars]
COPILOT_HOME = "$FLOX_ENV_CACHE/copilot"
COPILOT_API = "https://bot-api.flox.dev"
COPILOT_CANON_DB = "$FLOX_ENV_CACHE/copilot/canon.db"
COPILOT_MEMORY_DB = "$FLOX_ENV_CACHE/copilot/memory.db"
COPILOT_VOTE_QUEUE = "$FLOX_ENV_CACHE/copilot/votes.jsonl"
COPILOT_FEEDBACK_QUEUE = "$FLOX_ENV_CACHE/copilot/feedback.jsonl"

[hook]
on-activate = """
  # Initialize copilot state directories
  mkdir -p "$COPILOT_HOME"

  # Authenticate with FloxHub (reuse flox auth token)
  if [ -f "$HOME/.config/flox/floxhub_token" ]; then
    export COPILOT_TOKEN=$(cat "$HOME/.config/flox/floxhub_token")
  fi

  # Sync canon if online (non-blocking)
  if curl -s --max-time 2 "$COPILOT_API/health" > /dev/null 2>&1; then
    python "$FLOX_ENV_PROJECT/src/sync.py" --canon --memory --quiet &
  fi

  # Flush any queued votes/feedback from offline sessions
  if [ -s "$COPILOT_VOTE_QUEUE" ]; then
    python "$FLOX_ENV_PROJECT/src/sync.py" --flush-votes --quiet &
  fi
  if [ -s "$COPILOT_FEEDBACK_QUEUE" ]; then
    python "$FLOX_ENV_PROJECT/src/sync.py" --flush-feedback --quiet &
  fi
"""

[profile.common]
# The main co-pilot interface
copilot() {
  python "$FLOX_ENV_PROJECT/src/copilot.py" "$@"
}

# Quick question mode
ask() {
  copilot ask "$@"
}

# Interactive chat mode
copilot-chat() {
  copilot chat
}

# Diagnose current environment
copilot-diagnose() {
  copilot diagnose --context
}

# Submit field feedback (entitled users)
copilot-feedback() {
  copilot feedback "$@"
}

# Open a support ticket (entitled users)
copilot-ticket() {
  copilot ticket "$@"
}

# Sync state with central (manual trigger)
copilot-sync() {
  python "$FLOX_ENV_PROJECT/src/sync.py" --all
}
```

### Co-Pilot Modes

```
┌─────────────────────────────────────────────────────────────┐
│  Co-Pilot Operating Modes                                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ASK Mode (single-shot)                                │  │
│  │                                                        │  │
│  │  $ ask "how do I add a service to my manifest?"        │  │
│  │                                                        │  │
│  │  → Reads local .flox/env/manifest.toml                 │  │
│  │  → Detects skills from manifest                        │  │
│  │  → Queries central API (or local canon if offline)     │  │
│  │  → Returns answer with context-aware examples          │  │
│  │  → Prompts for vote                                    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  CHAT Mode (multi-turn)                                │  │
│  │                                                        │  │
│  │  $ copilot-chat                                        │  │
│  │  🤖 I see you're working on a Flox project with       │  │
│  │     terraform and aws. What can I help with?           │  │
│  │  > I need to set up a CI pipeline                      │  │
│  │  🤖 [loads skill:terraform + skill:aws, reviews        │  │
│  │     manifest, provides multi-step guidance]            │  │
│  │  > that worked, but now I'm seeing a conflict...       │  │
│  │  🤖 [maintains conversation context, deepens]          │  │
│  │                                                        │  │
│  │  Conversation persisted locally + synced to central    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  DIAGNOSE Mode (environment analysis)                  │  │
│  │                                                        │  │
│  │  $ copilot-diagnose                                    │  │
│  │                                                        │  │
│  │  → Reads manifest, env.json, lock files                │  │
│  │  → Checks for known anti-patterns                      │  │
│  │  → Identifies package conflicts                        │  │
│  │  → Suggests improvements based on detected skills      │  │
│  │  → Compares against known-good patterns from canon     │  │
│  │  → Reports findings with actionable suggestions        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  LEARN Mode (guided growth — entitled users)           │  │
│  │                                                        │  │
│  │  $ copilot learn                                       │  │
│  │  🤖 Based on your projects, here's what I'd suggest:  │  │
│  │     1. Your manifests don't use pkg-groups — this      │  │
│  │        will bite you as complexity grows. Want to       │  │
│  │        learn about package grouping?                   │  │
│  │     2. You're running 3 services but no health         │  │
│  │        checks. Want to add those?                      │  │
│  │     3. Your team isn't using composition yet — this    │  │
│  │        could reduce duplication across your 4 envs.    │  │
│  │                                                        │  │
│  │  Tracks progress: topics mastered, gaps identified,    │  │
│  │  skill level evolution over time.                      │  │
│  │                                                        │  │
│  │  Progress synced to central → informs support quality  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  FEEDBACK Mode (field feedback — entitled users)       │  │
│  │                                                        │  │
│  │  $ copilot-feedback "terraform state lock conflict     │  │
│  │    when using flox activate in CI. Workaround is X     │  │
│  │    but this should be documented."                     │  │
│  │                                                        │  │
│  │  → Classifies feedback (doc gap, feature req, bug)     │  │
│  │  → Attaches environment context automatically          │  │
│  │  → Queues for upstream submission                      │  │
│  │  → If offline, stored in COPILOT_FEEDBACK_QUEUE        │  │
│  │  → Flushed on next sync                                │  │
│  │                                                        │  │
│  │  This is structured field intelligence, not a ticket.  │  │
│  │  It feeds the canon improvement pipeline directly.     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  TICKET Mode (triaged support — entitled users)        │  │
│  │                                                        │  │
│  │  $ copilot-ticket                                      │  │
│  │  🤖 I'll gather context for a support ticket.          │  │
│  │     Describe the issue:                                │  │
│  │  > activation hangs after adding cuda packages         │  │
│  │  🤖 I've collected:                                    │  │
│  │     - Your manifest (sanitized)                        │  │
│  │     - Environment metadata                             │  │
│  │     - Flox version + system info                       │  │
│  │     - Related conversation history                     │  │
│  │     - Prior resolution attempts                        │  │
│  │     Suggested priority: P2 (degraded workflow)         │  │
│  │     Suggested category: package-conflict               │  │
│  │     Submit? [y/n]                                      │  │
│  │                                                        │  │
│  │  → Creates a well-triaged Intercom ticket              │  │
│  │  → Human support gets full context on first touch      │  │
│  │  → User gets ticket ID for tracking                    │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Co-Pilot ↔ Central Borg Connection

```
┌─────────────────────────────────────────────────────────────┐
│  Co-Pilot Sync Architecture                                  │
│                                                              │
│  LOCAL (Co-Pilot)                 CENTRAL (Borg)             │
│                                                              │
│  ┌──────────────────┐            ┌──────────────────┐       │
│  │ Local Canon      │◄───pull────│ Canon Engine     │       │
│  │ (SQLite +        │            │ (pgvector)       │       │
│  │  ChromaDB)       │            │                  │       │
│  │                  │            │ Full corpus +    │       │
│  │ Subset: core +   │            │ all skills +     │       │
│  │ user's active    │            │ all Q&A          │       │
│  │ skills only      │            │                  │       │
│  └──────────────────┘            └──────────────────┘       │
│                                                              │
│  ┌──────────────────┐            ┌──────────────────┐       │
│  │ Local Memory     │───push────►│ User Memory      │       │
│  │ (SQLite)         │◄───pull────│ Store            │       │
│  │                  │            │ (PostgreSQL)     │       │
│  │ Session history, │            │                  │       │
│  │ skill level,     │            │ Canonical        │       │
│  │ project patterns │            │ cross-channel    │       │
│  └──────────────────┘            │ memory           │       │
│                                  └──────────────────┘       │
│  ┌──────────────────┐            ┌──────────────────┐       │
│  │ Vote Queue       │───push────►│ Vote Pipeline    │       │
│  │ (JSONL file)     │            │ (Kafka topic)    │       │
│  └──────────────────┘            └──────────────────┘       │
│                                                              │
│  ┌──────────────────┐            ┌──────────────────┐       │
│  │ Feedback Queue   │───push────►│ Feedback         │       │
│  │ (JSONL file)     │            │ Pipeline         │       │
│  └──────────────────┘            │ (Intercom /      │       │
│                                  │  Canon forge)    │       │
│  ┌──────────────────┐            └──────────────────┘       │
│  │ Ticket Drafts    │───push────►┌──────────────────┐       │
│  │ (JSONL file)     │            │ Intercom Bridge  │       │
│  └──────────────────┘            └──────────────────┘       │
│                                                              │
│  Sync triggers:                                              │
│  • On activate (background, non-blocking)                    │
│  • Manual: copilot-sync                                      │
│  • On ticket/feedback submit (foreground, must succeed)      │
│  • Periodic: every 4 hours if session active                 │
│                                                              │
│  Offline behavior:                                           │
│  • Canon: uses last-synced local copy (L1 capable)           │
│  • Memory: writes locally, syncs on reconnect                │
│  • Votes/feedback: queued as JSONL, flushed on sync          │
│  • Tickets: queued, submitted on next connectivity           │
│  • Skills: uses cached skill packages                        │
│  • LLM: falls back to local model (degraded) or             │
│    queues request for when connectivity returns              │
└─────────────────────────────────────────────────────────────┘
```

### FloxHub Auth Integration

The co-pilot piggybacks on existing `flox auth`:

```
$ flox auth login
# User authenticates with FloxHub
# Token stored at ~/.config/flox/floxhub_token

$ flox activate  # (in copilot environment)
# Hook reads FloxHub token
# Validates against Central API
# Resolves entitlement tier
# Downloads user's cross-channel memory
# Syncs appropriate canon subset
```

**Why FloxHub auth matters:**
- Single identity across CLI, co-pilot, and FloxHub
- Entitlement tier resolved from FloxHub account status
- Same identity links to Slack/Discord/email via the cross-channel map
- Environment metadata (which envs the user has published/pulled) enriches context

### What the Co-Pilot Sends Upstream

The co-pilot is a **meaningful signal source** for the central borg, not just a consumer:

```
┌─────────────────────────────────────────────────────────────┐
│  Upstream Signal from Co-Pilot                               │
│                                                              │
│  1. VOTES                                                    │
│     Same as any channel — labeled training data              │
│                                                              │
│  2. LEARNING PROGRESS                                        │
│     "User mastered services, struggling with composition"    │
│     → Informs skill-level calibration across all channels    │
│     → Identifies which docs/skills need better onramps      │
│                                                              │
│  3. FIELD FEEDBACK (entitled)                                │
│     Structured, contextualized product intelligence          │
│     "Terraform + Flox activate conflict in CI"              │
│     → Feeds canon gap detection                              │
│     → May trigger doc updates or skill revisions             │
│     → Richer signal than raw Intercom tickets                │
│                                                              │
│  4. ENVIRONMENT TELEMETRY (opt-in)                           │
│     Anonymized: which packages, which skills, which          │
│     patterns. Never code, never secrets.                     │
│     → Powers "popular patterns" and skill demand signals     │
│     → Informs which skill packages to prioritize             │
│                                                              │
│  5. DIAGNOSTIC PATTERNS                                      │
│     When copilot-diagnose runs, the findings (anonymized)    │
│     reveal common anti-patterns across the user base         │
│     → "40% of users aren't using pkg-groups" → proactive    │
│       canon improvement                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Entitlement Model

Entitlements are resolved via FloxHub auth and cached in Redis for fast lookup. The Central API gates features based on tier.

```
┌─────────────────────────────────────────────────────────────┐
│  Entitlement Tiers                                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  COMMUNITY (free, FloxHub account)                     │  │
│  │                                                        │  │
│  │  ✓ L1 support (all channels)                           │  │
│  │  ✓ Basic skill detection + loading                     │  │
│  │  ✓ Vote on responses                                   │  │
│  │  ✓ CLI ask/chat modes                                  │  │
│  │  ✓ Local canon (core only, no skill packages)          │  │
│  │  ✓ Basic cross-channel memory (last 30 days)           │  │
│  │                                                        │  │
│  │  ✗ No co-pilot learn mode                              │  │
│  │  ✗ No ticket creation (must use Intercom directly)     │  │
│  │  ✗ No field feedback pipeline                          │  │
│  │  ✗ No environment telemetry                            │  │
│  │  ✗ Rate limited (N queries/day)                        │  │
│  │                                                        │  │
│  │  Escalation: Basic ticket via Intercom widget only.    │  │
│  │  No auto-triage, no context bundle.                    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  PRO (paid individual or team plan)                    │  │
│  │                                                        │  │
│  │  Everything in Community, plus:                        │  │
│  │                                                        │  │
│  │  ✓ L2 support (multi-turn, deep debugging)             │  │
│  │  ✓ Full skill package library                          │  │
│  │  ✓ Co-pilot learn mode (guided growth paths)           │  │
│  │  ✓ Co-pilot diagnose mode                              │  │
│  │  ✓ Triaged ticket creation (copilot-ticket)            │  │
│  │    → Auto-context, auto-triage, priority routing       │  │
│  │  ✓ Field feedback pipeline (copilot-feedback)          │  │
│  │    → Structured, feeds canon directly                  │  │
│  │  ✓ Full cross-channel memory (unlimited history)       │  │
│  │  ✓ Local canon with skill packages                     │  │
│  │  ✓ Higher rate limits                                  │  │
│  │  ✓ Codex access for code generation                    │  │
│  │                                                        │  │
│  │  Escalation: Smart ticket via copilot-ticket.          │  │
│  │  Full context bundle, suggested priority + category.   │  │
│  │  Human support gets everything on first touch.         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ENTERPRISE (org-wide plan)                            │  │
│  │                                                        │  │
│  │  Everything in Pro, plus:                              │  │
│  │                                                        │  │
│  │  ✓ Org-wide knowledge layer                            │  │
│  │    → Bot learns org-specific patterns                  │  │
│  │    → "Your org's terraform modules use pattern X"      │  │
│  │  ✓ Custom skill packages (org-authored)                │  │
│  │    → "skill:acme-infra" with org-specific guidance     │  │
│  │  ✓ SSO-based identity (SAML/OIDC → FloxHub)           │  │
│  │  ✓ Admin dashboard                                     │  │
│  │    → Org-wide usage, common issues, skill adoption     │  │
│  │  ✓ Priority escalation routing                         │  │
│  │    → Dedicated support queue, SLA tracking             │  │
│  │  ✓ Environment telemetry dashboard                     │  │
│  │    → What packages/patterns are your teams using?      │  │
│  │  ✓ Bulk field feedback (aggregate org insights)        │  │
│  │  ✓ Private Slack/Discord bot instance (org-only)       │  │
│  │                                                        │  │
│  │  Escalation: Priority queue with SLA. Context bundle   │  │
│  │  includes org-wide pattern matching ("3 other teams    │  │
│  │  in your org hit this same issue this month").          │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Entitlement Resolution Flow

```
Request arrives at Central API
         │
         ▼
┌──────────────────────────────┐
│  Extract identity            │
│  (FloxHub token, Slack ID,   │
│   Discord ID, email)         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Check Redis cache           │
│  Key: canonical_user_id      │
│  TTL: 1 hour                 │
└──────────────┬───────────────┘
               │
          Cache miss?
               │
               ▼
┌──────────────────────────────┐
│  Query FloxHub API           │
│  GET /users/{id}/entitlement │
│                              │
│  Returns:                    │
│  {                           │
│    tier: "pro",              │
│    org_id: "acme-corp",      │
│    features: [...],          │
│    rate_limits: {...},       │
│    expires_at: "..."         │
│  }                           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Cache in Redis              │
│  Apply feature gates         │
│  Route to appropriate        │
│  processing pipeline         │
└──────────────────────────────┘
```

### Why Entitlements Matter for the System

The entitlement model isn't just a billing gate — it changes what signals flow upstream:

```
Community users → votes only (volume signal)
Pro users       → votes + feedback + tickets + telemetry (rich signal)
Enterprise      → all of the above + org-level patterns (strategic signal)
```

The richest signal comes from entitled users. Their field feedback is structured and contextualized. Their tickets are pre-triaged. Their learning progress reveals where the product's onboarding gaps are. This creates a natural flywheel: paying users contribute the highest-quality signal, which improves the canon, which improves the experience for everyone.

---

## 9. Feedback Loop Architecture

### Vote Collection

Every response gets vote affordances appropriate to the channel:

| Channel | Vote UX |
|---------|---------|
| Slack | Block Kit buttons: ✅ Helpful / ❌ Not helpful / 🎫 Escalate |
| Discord | Component buttons: 👍 Helpful / 👎 Not helpful / 📋 Ticket |
| CLI | Inline prompt: "Was this helpful? [y/n/skip]" |
| Co-Pilot | Same as CLI, plus copilot vote --last up/down |
| Email | Footer links hitting webhook endpoint |

### Vote Processing Pipeline

```
Vote received
    │
    ▼
Store raw vote + full context snapshot
    │
    ▼
Publish to Kafka: floxbot.votes
    │
    ├─→ Flink Job 1: Windowed vote aggregation
    │     → Per-topic vote rates
    │     → Per-skill vote rates
    │     → Per-user satisfaction trend
    │     → Anomaly alerts (sudden downvote spike)
    │
    ├─→ Dashboard consumer → real-time metrics
    │
    ├─→ Daily aggregation job
    │     ├─→ High-vote responses → Tier 2 candidate Q&A
    │     ├─→ Downvote clusters → Canon gap detection
    │     ├─→ User skill calibration
    │     └─→ Skill package performance scores
    │
    └─→ Weekly upstream export (anonymized)
          ├─→ Candidate fine-tuning pairs
          ├─→ Canon correction suggestions
          └─→ New Q&A entries for RAG corpus
```

### The Upstream Contract

Users opt in to upstream contribution. The export is:
- **Anonymized**: No user IDs, no project-specific code
- **Curated**: Only high-confidence entries (strong vote signal)
- **Structured**: `(query_category, query_template, response_template, vote_score)`
- **Reviewed**: Human review gate before canon merge

### Field Feedback Pipeline (Pro/Enterprise)

```
copilot-feedback "description..."
         │
         ▼
┌──────────────────────────────────┐
│  Feedback Processor              │
│                                  │
│  1. Classify:                    │
│     - doc_gap                    │
│     - feature_request            │
│     - bug_report                 │
│     - pattern_suggestion         │
│     - skill_improvement          │
│                                  │
│  2. Enrich:                      │
│     - Attach manifest context    │
│     - Attach environment info    │
│     - Attach relevant convo      │
│     - Attach user skill level    │
│                                  │
│  3. Route:                       │
│     doc_gap → Canon forge queue  │
│     feature_request → PM board   │
│     bug_report → Engineering     │
│     pattern_suggestion → Canon   │
│     skill_improvement → Skill    │
│       package maintainer         │
└──────────────────────────────────┘
```

---

## 10. Cross-Channel Identity and Awareness

### Identity Resolution

```
┌─────────────────────────────────────────────┐
│  Identity Resolution                        │
│                                             │
│  Primary keys:                              │
│  - FloxHub username (strongest — from auth) │
│  - Email (from Slack workspace, Discord     │
│    verified, email channel, CLI auth)       │
│                                             │
│  Linking flow:                              │
│  1. User auths co-pilot → FloxHub ID       │
│  2. Same email on Slack → auto-link         │
│  3. User can manually link accounts         │
│     via /floxbot link or copilot link       │
│                                             │
│  All memory/votes/history unified under     │
│  single canonical user_id                   │
└─────────────────────────────────────────────┘
```

### Cross-Channel Awareness Rules

When Bot A sees a question from User A in Channel A, and Bot B sees User A in Channel B working on the same thing, the system should be smart about it — but not creepy.

**Confidence tiers for surfacing:**

**HIGH CONFIDENCE — always surface:**
Same canonical_user_id + same topic (semantic similarity > 0.85) + within 24 hours.

→ "I see you were working through a similar terraform issue in Slack earlier. Want to pick up where we left off?"

Why surface: Saves user from repeating context. The value is obvious.

**MEDIUM CONFIDENCE — surface gently:**
Same canonical_user_id + related topic (similarity 0.60-0.85) + within 72 hours.

→ "This might be related to the k8s deployment issue you mentioned recently — is this the same project?"

Why hedge: Could be a different project. Ask, don't assume.

**LOW CONFIDENCE — use silently:**
Same canonical_user_id + loosely related (similarity 0.40-0.60) + any timeframe.

→ Don't mention it. Use prior context to inform response quality (skill level, preferred tools, past issues).

Why silent: Surfacing would feel surveillance-y. Using it silently just makes the bot smarter.

**NEVER surface:**
- Unlinked accounts (no confirmed identity match)
- Private DMs referenced in public channels
- Anything that reveals the user was in a specific channel

**Privacy rule:** Cross-channel surfacing only in DMs or private contexts. In public channels, use context silently or not at all.

### The Privacy Contract

1. **Know it exists** — onboarding explains cross-channel memory
2. **Control it** — `/floxbot privacy` or `copilot privacy` shows linked accounts, lets you unlink
3. **Scope it** — "Don't share context from my DMs" should be a setting
4. **Benefit from it** — the value proposition must be obvious (not repeating yourself)

---

## 11. Kafka and Flink: The Event Backbone

### Where Kafka Earns Its Keep

Kafka serves as the event backbone for async side effects. It does NOT sit in the user-facing hot path.

**Topics:**

| Topic | Purpose | Key |
|-------|---------|-----|
| `floxbot.messages.inbound` | All normalized messages, all channels | conversation_id |
| `floxbot.messages.outbound` | Bot responses, routed to adapters | channel + user_id |
| `floxbot.votes` | All vote events (structured) | user_id |
| `floxbot.context.detected` | Skill detection, project context snapshots | user_id |
| `floxbot.escalations` | Ticket creation events → Intercom consumer | conversation_id |
| `floxbot.canon.updates` | Canon refresh events | — |
| `floxbot.sessions.xc` | Cross-channel session correlations | canonical_user_id |
| `floxbot.feedback` | Field feedback from co-pilot | user_id |
| `floxbot.copilot.telemetry` | Anonymized environment telemetry | — |

**The value of Kafka here:**
- Decouples adapters from the brain (adapters can be down without losing messages)
- Replay capability (reprocess yesterday's messages with today's improved canon)
- Fan-out (votes go to: vote store, dashboard, anomaly detector simultaneously)
- Ordering guarantees per conversation
- Natural audit trail
- Cross-channel event correlation

### Where Kafka is NOT Used

The user-facing request/response path stays synchronous HTTP:

```
Adapter → HTTP POST to Central API → LLM call → HTTP response → Adapter
```

After the response is sent, side effects are published to Kafka asynchronously:

```
      ┌─────────────────┐
      │  User sends msg  │
      └────────┬────────┘
               │
   ┌───────────┼───────────┐
   │           │           │
   ▼           ▼           ▼
┌────────┐ ┌─────────┐ ┌─────────┐
│ Sync:  │ │ Async:  │ │ Async:  │
│ HTTP → │ │ Publish │ │ Publish │
│ API →  │ │ to      │ │ context │
│ LLM →  │ │ Kafka   │ │ event   │
│ reply  │ │ (audit) │ │         │
└────────┘ └─────────┘ └─────────┘
     │
     ▼ (after response sent)
Publish response + metadata to Kafka
```

### Flink Jobs

**Job 1: Vote Aggregation**
Source: `floxbot.votes`. Window: Tumbling 1-hour + Sliding 24-hour.
Output: Per-topic rates, per-skill rates, per-user satisfaction, anomaly alerts.
Why: Sudden downvote spike after a release = immediate early warning.

**Job 2: Cross-Channel Session Correlation**
Source: `floxbot.messages.inbound` (all channels). Window: Session, 30-min gap. Key: canonical_user_id.
Logic: Same user + similar topic within window → emit cross-channel session event.
This is what powers the "I see you were asking about this in Slack" behavior.

**Job 3: Canon Gap Detection**
Source: `floxbot.votes` + `floxbot.context.detected`. Window: Daily tumbling.
Logic: Cluster downvoted queries by topic, cross-reference with skill coverage.
Output: "skill:terraform has 40% downvote rate on Terraform Cloud integration questions."

**Job 4: Trending Issues**
Source: `floxbot.messages.inbound`. Window: Sliding 4-hour.
Logic: Detect sudden spikes in similar queries/error signatures.
Output: Alert to team Slack channel. "10 users hit the same error in 2 hours — possible release regression."

---

## 12. Canon Management

### The Canon Forge

A Flox-managed environment where bot knowledge is built, tested, and validated.

```toml
# flox/support-bot-canon/.flox/env/manifest.toml
[install]
python.pkg-path = "python311Full"
uv.pkg-path = "uv"
postgresql.pkg-path = "postgresql"
jq.pkg-path = "jq"

[vars]
CANON_SOURCE = "$FLOX_ENV_PROJECT/canon"
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_DB = "postgresql://localhost:5432/canon"

[services.postgres]
command = "postgres -D $FLOX_ENV_CACHE/pgdata -p 5432"
is-daemon = true

[hook]
on-activate = """
  if [ ! -f "$FLOX_ENV_CACHE/.canon_indexed" ]; then
    python "$FLOX_ENV_PROJECT/scripts/index_canon.py"
    touch "$FLOX_ENV_CACHE/.canon_indexed"
  fi
"""
```

This is where you:
1. **Ingest canon sources** (docs, skills, resolved tickets)
2. **Generate embeddings** and validate retrieval quality
3. **Run eval harnesses** — feed known questions, verify answers against ground truth
4. **Test new skill additions** before they go live
5. **Process upstream vote exports** into canon improvements

### Refresh Schedule

| Source | Trigger | Method |
|--------|---------|--------|
| Flox docs | Git push webhook | Re-chunk → re-embed |
| SKILL.md files | Nightly cron | Pull from source → re-embed |
| Skill packages | On publish to FloxHub | Re-embed skill corpus |
| Q&A pairs | Daily aggregation | Vote pipeline output → embed |
| Release notes | Release webhook | Append → embed |
| Intercom tickets | Weekly export | Filter resolved → embed |
| Field feedback | On review/approval | Route to appropriate canon section |

### Local Canon (CLI/Co-Pilot Offline)

```bash
# User manually syncs local canon
$ copilot-sync

# Or auto-sync on activate (if online, non-blocking)
# In hook:
if curl -s --max-time 2 "$COPILOT_API/health" > /dev/null 2>&1; then
  python "$FLOX_ENV_PROJECT/src/sync.py" --canon --memory --quiet &
fi
```

Local canon is a SQLite + ChromaDB snapshot. Contains core Flox canon plus skill packages matching the user's detected needs. Enough for L1 support offline. L2 queries gracefully degrade with "I can give you a partial answer offline — connect for full support."

---

## 13. Flox Environment Topology

```
flox/
├── support-bot-canon/        # Canon forge (build/test knowledge)
│   └── .flox/env/manifest.toml
│
├── support-bot-api/          # Central API service
│   └── .flox/env/manifest.toml
│
├── support-bot-slack/        # Slack adapter
│   └── .flox/env/manifest.toml
│
├── support-bot-discord/      # Discord adapter
│   └── .flox/env/manifest.toml
│
├── support-bot-email/        # Email adapter
│   └── .flox/env/manifest.toml
│
├── support-bot-cli/          # CLI tool (lightweight, distributed)
│   └── .flox/env/manifest.toml
│
├── support-bot-copilot/      # Co-Pilot (local-first, FloxHub auth)
│   └── .flox/env/manifest.toml
│
├── support-bot-kafka/        # Kafka + Zookeeper
│   └── .flox/env/manifest.toml
│
├── support-bot-flink/        # Flink job manager + task manager
│   └── .flox/env/manifest.toml
│
├── support-bot-shared/       # Shared types, configs, MCP server
│   └── .flox/env/manifest.toml
│
└── skill packages (on FloxHub):
    ├── floxbot/core-canon
    ├── floxbot/skill-k8s
    ├── floxbot/skill-terraform
    ├── floxbot/skill-aws
    ├── floxbot/skill-gcp
    ├── floxbot/skill-docker
    ├── floxbot/skill-postgres
    ├── floxbot/skill-rust
    └── floxbot/skill-python
```

Each environment is independently deployable, version-pinnable, and composable. The shared environment provides common dependencies and the MCP server definition.

---

## 14. Build Order

### Phase 1: Foundation
- Central API skeleton with single LLM backend (Claude)
- Canon ingest pipeline (docs + skills)
- RAG retrieval (pgvector + basic chunking)
- CLI adapter (simplest I/O, fastest iteration)
- FloxHub auth integration
- Vote collection (store only, no aggregation yet)

### Phase 2: Co-Pilot + Entitlements
- Co-Pilot environment (ask + chat + diagnose modes)
- Entitlement gate in Central API
- Local canon sync (SQLite + ChromaDB)
- Local memory persistence
- Offline vote/feedback queuing

### Phase 3: Multi-Channel
- Slack adapter (Socket Mode, Block Kit)
- Discord adapter (Gateway, Forum channel)
- Email adapter (SendGrid inbound parse)
- Cross-channel identity linking
- Intercom escalation bridge
- L1/L2 classification

### Phase 4: Intelligence
- Codex integration (dual LLM routing)
- Skill detection engine + dynamic loading
- User memory (Tier 1) across channels
- Instance knowledge aggregation (Tier 2)
- MCP server for live Flox operations

### Phase 5: Streaming + Feedback
- Kafka event backbone
- Flink jobs (vote aggregation, cross-channel correlation, canon gaps, trending)
- Field feedback pipeline (Pro/Enterprise)
- Triaged ticket creation (copilot-ticket)
- Co-pilot learn mode (guided growth)

### Phase 6: Enterprise
- Org-wide knowledge layer
- Custom skill packages
- SSO integration
- Admin dashboard
- Priority escalation routing
- Environment telemetry

---

## 15. Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend pattern | Shared central API | Unified memory, single canon source, consistent behavior across all channels |
| Co-Pilot architecture | Local-first Flox env with sync | Must work offline; FloxHub auth for identity; sync for richness |
| CLI vs Co-Pilot | Separate environments | CLI is lightweight (ask/chat); Co-Pilot is full-featured (learn/diagnose/ticket/feedback) |
| FloxHub auth | Piggyback on `flox auth` | No new auth flow; single identity; entitlement resolution |
| Entitlement model | Community / Pro / Enterprise | Natural value gradient; richest signal from paying users; flywheel effect |
| LLM routing | Intent-based, Claude primary | Claude for conversation + orchestration + teaching; Codex for code gen |
| Skill loading | Dynamic, max 2 per turn | Context window budget; primary + secondary skill model |
| Skill packaging | Flox environments on FloxHub | Version-pinned, composable, independently testable |
| Slack bot identity | Slack App via Socket Mode | Simplest deployment, no public endpoint |
| Discord bot identity | Bot Application via Gateway | Standard pattern; Forum channel for structured support |
| Kafka | Event backbone (async side effects only) | Decoupling, replay, fan-out, audit, cross-channel correlation |
| Kafka in hot path | NO | Latency matters; sync HTTP for user-facing path |
| Flink | 4 streaming jobs | Vote aggregation, x-channel correlation, canon gaps, trending issues |
| Vector store | pgvector → Qdrant at scale | pgvector ships easily in Flox; Qdrant when volume demands |
| User identity | FloxHub username primary, email fallback | Most universal; strongest cross-channel link |
| Cross-channel surfacing | Confidence-tiered | High=mention, medium=ask, low=silent; never in public channels |
| Cross-channel privacy | Explicit, user-controlled | Must know, must control, must benefit |
| Vote → training | Anonymized weekly export with human review | Privacy + quality gate before canon merge |
| Field feedback | Structured pipeline, Pro/Enterprise | Richest signal source; feeds canon directly; worth paying for |
| Ticket creation | Bot-triaged, context-bundled, Pro/Enterprise | Humans get full context on first touch; entitled users get priority |
| Canon refresh | Event-driven + scheduled | Docs on push, aggregates on schedule, skills on publish |
| Local canon | SQLite + ChromaDB snapshot | Lightweight, offline-capable, syncs subset based on user's skills |

---

## Full System Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  Slack   │  │ Discord  │  │  Email   │  │   CLI    │  │ Co-Pilot │  │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ (local)  │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │              │              │              │              │       │
│       └──────────────┴──────┬───────┴──────────────┴──────────────┘       │
│                             │                                            │
│                             │  Normalized messages                       │
│                             │  (with entitlement tier)                   │
│                             │                                            │
│   ┌─────────────────────────┴───────────────────────────────────┐        │
│   │  Kafka Event Bus                                            │        │
│   │  .inbound │ .outbound │ .votes │ .context │ .escalations   │        │
│   │  .canon.updates │ .sessions.xc │ .feedback │ .telemetry    │        │
│   └───────┬───────────┬───────────┬─────────────────────────────┘        │
│           │           │           │                                      │
│     ┌─────┴──┐  ┌─────┴──┐  ┌────┴─────────────────────────────────┐    │
│     │ Flink  │  │ Flink  │  │ Central API (sync HTTP path)         │    │
│     │ Vote   │  │ X-Chan │  │                                      │    │
│     │ Agg +  │  │ Corr + │  │ Auth + Entitlement Gate              │    │
│     │ Canon  │  │ Trend  │  │   ↓                                  │    │
│     │ Gaps   │  │ Detect │  │ Context Engine (user, project, xc)   │    │
│     └────────┘  └────────┘  │   ↓                                  │    │
│                             │ Skill Detection + Dynamic Loading    │    │
│                             │   ↓                                  │    │
│                             │ Router (Claude | Codex | Co-Pilot)   │    │
│                             │   ↓                                  │    │
│                             │ ┌──────────┐  ┌──────────────────┐   │    │
│                             │ │ Canon +  │  │ Skill Packages   │   │    │
│                             │ │ RAG      │  │ (dynamic load)   │   │    │
│                             │ └──────────┘  └──────────────────┘   │    │
│                             │   ↓                                  │    │
│                             │ User Memory + X-Channel Context      │    │
│                             │   ↓                                  │    │
│                             │ LLM (Claude | Codex)                 │    │
│                             │   ↓                                  │    │
│                             │ Response → Adapter                   │    │
│                             └──────────────────────────────────────┘    │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────┐       │
│   │  Data Layer                                                  │       │
│   │  PostgreSQL │ pgvector │ Redis │ S3/R2                       │       │
│   └─────────────────────────────────────────────────────────────┘       │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────┐       │
│   │  Canon Forge (Flox env)                                      │       │
│   │  Skill packages • Embedding pipeline • Eval harness          │       │
│   └─────────────────────────────────────────────────────────────┘       │
│                                                                         │
│   ┌───────────────────────┐  ┌──────────────────────────────────┐       │
│   │  Intercom Bridge      │  │  Feedback Pipeline               │       │
│   │  Tickets + escalation │  │  Field intel → Canon / PM / Eng  │       │
│   └───────────────────────┘  └──────────────────────────────────┘       │
│                                                                         │
│   All infrastructure managed by Flox environments.                      │
│   All skill packages versioned and published via FloxHub.               │
│   All auth via FloxHub. All entitlements resolved at request time.      │
└─────────────────────────────────────────────────────────────────────────┘
```
