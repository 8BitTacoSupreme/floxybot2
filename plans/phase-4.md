# Phase 4: Intelligence — Codex, Skills, User Memory, Instance Knowledge

## Context

Phases 1-3 are committed (245 tests passing). The hot path works: auth → context → skill detection → intent → Claude → response. But the "intelligence" layer is skeletal — Codex routes to Claude, skill packages are empty, user memory is never updated after interactions, and instance knowledge uses keyword matching instead of embeddings. Phase 4 makes FloxBot smart.

---

## Tasks (10 total)

### I1: Codex LLM Backend

**File:** `support-bot-api/src/llm/codex.py` (currently 30-line stub routing to Claude)

**Implement:**
- Full Codex backend mirroring `claude.py` structure:
  - `call_codex(message, context, skills, intent)` with its own system prompt
  - Code-focused system prompt: manifest editing, hook writing, script generation, debugging
  - Same tool-use loop as Claude (MCP_TOOLS, max 3 rounds, 45s timeout)
  - Code block extraction with language detection
  - Confidence scoring weighted toward code quality signals
- Codex system prompt (`CODEX_SYSTEM_PROMPT` in `prompts.py`):
  - Emphasize: output working code, use Flox conventions, show complete manifest sections
  - Include: manifest.toml schema reference, common hook patterns, service definitions
  - Tone: direct, minimal prose, code-first

**Config:** Uses `settings.CODEX_API_KEY` and `settings.CODEX_MODEL` (already defined in config.py)

**Test:** `tests/test_codex.py` — mock Anthropic client, verify code-focused system prompt, verify tool-use loop, verify entitlement gating routes community users to Claude.

---

### I2: Intent Classification Refinement

**File:** `support-bot-api/src/router/intent.py` (currently 45-line heuristic)

**Enhance:**
- Multi-signal confidence scoring instead of first-match keywords:
  - Code blocks present → +0.4 CODE_GENERATION
  - `manifest`, `hook`, `service`, `write`, `generate`, `create`, `edit` → +0.3 CODE_GENERATION
  - `error`, `debug`, `failing`, `broken`, `not working`, `diagnose`, `logs` → +0.3 DIAGNOSTIC
  - `how`, `explain`, `teach`, `learn`, `why`, `what is`, `guide` → +0.3 TEACHING
  - Question mark + no code → +0.2 CONVERSATIONAL
- HYBRID handling: if top two intents are within 0.1 of each other, route to Claude with both intent hints (Claude orchestrates, can delegate to Codex)
- Escalation signals: `billing`, `account`, `security`, `refund`, `cancel` → force ESCALATION (returns canned response + creates ticket)
- Return confidence score with intent for downstream use

**Test:** `tests/test_intent_classification.py` — parametrized tests for each intent type, hybrid detection, escalation override.

---

### I3: Prompt Variants for All Intents

**File:** `support-bot-api/src/llm/prompts.py` (currently 119 lines with single base prompt)

**Add:**
- `CODEX_SYSTEM_PROMPT` — Code generation focus:
  - Always output complete, working code blocks
  - Use Flox manifest.toml conventions
  - Show `[hook]`, `[services]`, `[install]` sections completely
  - When editing manifests, show before/after or the full section
- `DIAGNOSTIC_PROMPT_SUFFIX` — Structured debugging:
  - Start with "What I see" → "What might be wrong" → "Steps to fix"
  - Ask for `flox activate` output, error messages, manifest contents if not provided
  - Suggest diagnostic commands (`flox list`, `flox show`, `flox activate --verbose`)
- `TEACHING_PROMPT_SUFFIX` — Guided learning:
  - Break concepts into steps
  - Use analogies for Nix concepts
  - End with "Try it yourself" commands
  - Adjust depth based on `user_memory.skill_level`
- `CODE_GENERATION_PROMPT_SUFFIX` — For Claude when Codex unavailable:
  - Focus on code quality, completeness, manifest validity

**Modify `build_system_prompt()`:**
- Accept intent as `Intent` enum instead of string
- Select base prompt (SYSTEM_PROMPT_BASE vs CODEX_SYSTEM_PROMPT) based on backend
- Append intent-specific suffix
- Inject skill prompts from `skill.prompts[]` (diagnostic/pattern fragments)

**Test:** Extend `tests/test_prompt_labels.py` — verify each intent gets correct prompt assembly.

---

### I4: Skill Package Content (8 packages)

**Directories:** `skills/skill-{k8s,terraform,aws,gcp,docker,postgres,rust,python}/`

Each package needs:
```
skill-<name>/
├── SKILL.md          — 1-2k tokens of Flox-specific guidance for this technology
├── metadata.json     — {name, version, triggers, weight, description}
└── prompts/
    └── diagnostic.md — Common debugging patterns for this tech + Flox
```

**Content guidelines per skill:**
- **SKILL.md**: How to use this technology with Flox. Package names, common manifest patterns, hook examples, gotchas. NOT a general tutorial.
- **metadata.json**: `{name, version: "0.1.0", triggers: [...], weight: 1.0, description: "..."}`
- **prompts/diagnostic.md**: "When debugging X with Flox, check Y first" patterns.

**Skill-specific notes:**
| Skill | Key packages | Flox-specific content |
|-------|-------------|----------------------|
| k8s | kubectl, helm, kustomize | Kind cluster setup, kubeconfig in hooks, namespace management |
| terraform | terraform, opentofu | State management in `$FLOX_ENV_CACHE`, provider caching, LocalStack |
| aws | awscli2, aws-vault | Credential management, profile switching in hooks, LocalStack |
| gcp | google-cloud-sdk | gcloud auth in hooks, project switching |
| docker | docker, podman | `flox containerize`, Dockerfile → manifest migration, bind mounts |
| postgres | postgresql_16, pgcli | Service definition, data dir in `$FLOX_ENV_CACHE`, pgvector |
| rust | rustc, cargo | Rust toolchain in Flox, cross-compilation, cargo caching |
| python | python3, uv, pip | Venv in `$FLOX_ENV_CACHE`, pyproject.toml alongside manifest, pip caching |

**Test:** `tests/test_skill_packages.py` — validate all 8 packages have SKILL.md + metadata.json, metadata.json parses correctly, triggers match SKILL_TRIGGERS keys.

---

### I5: Skill Detection — Manifest Inspection

**File:** `support-bot-api/src/skills/loader.py` (currently 135 lines)

**Add `_inspect_manifest()` function:**
- Parse manifest TOML from `context.project_context.manifest`
- Extract `[install]` package names
- Map packages to skills via a `PACKAGE_SKILL_MAP`:
  ```python
  PACKAGE_SKILL_MAP = {
      "kubectl": "k8s", "helm": "k8s", "kustomize": "k8s", "kind": "k8s",
      "terraform": "terraform", "opentofu": "terraform",
      "awscli2": "aws", "aws-vault": "aws", "aws-sam-cli": "aws",
      "google-cloud-sdk": "gcp",
      "docker": "docker", "podman": "docker", "docker-compose": "docker",
      "postgresql": "postgres", "postgresql_16": "postgres", "pgcli": "postgres",
      "rustc": "rust", "cargo": "rust",
      "python3": "python", "uv": "python", "poetry": "python",
  }
  ```
- Return detected skills with confidence 3.0 (highest — manifest is ground truth)

**Add `_load_metadata()` function:**
- Load `metadata.json` from skill directory
- Use `triggers` field to supplement `SKILL_TRIGGERS` at startup
- Use `weight` field as a multiplier on detection score

**Enhance `detect_and_load_skills()`:**
- Insert manifest inspection as step 0 (before project context)
- Load `prompts/diagnostic.md` into `SkillPackage.prompts[]` when intent is DIAGNOSTIC
- Load `qa/common.json` into `SkillPackage.qa_pairs[]` when available

**Test:** Extend `tests/test_skill_loader.py` — manifest inspection with various package combos, metadata loading, prompt fragment injection.

---

### I6: User Memory Updates Post-Interaction

**File:** `support-bot-api/src/memory/user.py` (currently 84 lines with get/update stubs)

**Add `build_memory_update()` function:**
- Called after every successful LLM response
- Extracts from the interaction:
  - `skills_used` → append to `recent_skills` (keep last 10, dedup)
  - `intent` → if TEACHING, track topics learned
  - `project_context.detected_skills` → update `projects` map
  - If user asked about a new technology → update `projects` with tech name
- Skill level inference (simple heuristic):
  - Count of total interactions → beginner (<10), intermediate (10-50), advanced (50+)
  - Override: if user submits manifests or code blocks regularly → intermediate+
- Does NOT re-derive existing fields, only merges new data

**Wire into `main.py`:**
- After step 5 (route_to_backend), call `build_memory_update()` and `update_user_memory()`
- Best-effort: wrap in try/except, log failures, don't block response

**Add `recent_skills` field to `UserMemory` model:**
- `recent_skills = Column(JSON, default=list)` in `db/models.py`
- Alembic migration `005_user_memory_recent_skills.py`

**Test:** `tests/test_user_memory_updates.py` — verify skills tracking, project extraction, skill level progression, merge behavior.

---

### I7: Instance Knowledge with Embedding Search

**File:** `support-bot-api/src/rag/engine.py` — enhance `query_instance_knowledge()`

**Replace keyword matching with embedding search:**
- Embed the query using `_embed_query()` (same Voyage function used for canon RAG)
- Store query embeddings in a new `vote_embeddings` table (or add `query_embedding` column to Vote)
- Cosine similarity search against stored query embeddings
- Rank by: similarity × vote_ratio (upvotes / total_votes)
- Return top_k results with source="instance_knowledge"

**Deferred approach (simpler, no schema change):**
- For now, embed the query at search time
- Embed each candidate vote's `query_text` on-the-fly (expensive but functional for small vote sets)
- Cache popular query embeddings in Redis (key: hash of query_text, TTL 24h)
- Phase 5 Flink job will pre-compute and store these properly

**Wire into context engine:**
- In `context/engine.py build_context()`, call `query_instance_knowledge()` after canon RAG
- Add results to a new `BuiltContext.instance_knowledge` field
- Inject into system prompt via `build_system_prompt()`

**Test:** `tests/test_instance_knowledge.py` — mock Voyage client, verify similarity-based ranking beats keyword matching.

---

### I8: Context Engine — Instance Knowledge Integration

**File:** `support-bot-api/src/context/engine.py` (currently 73 lines)

**Add step 2b after RAG query:**
```python
# 2b. Instance knowledge (Tier 2) — upvoted Q&A pairs
if text and session is not None and entitlements.memory_enabled:
    try:
        from ..rag.engine import query_instance_knowledge
        context.instance_knowledge = await query_instance_knowledge(
            text, session=session, top_k=3
        )
    except Exception as e:
        logger.warning("Instance knowledge query failed: %s", e)
```

**Add `instance_knowledge` to `BuiltContext`:**
```python
instance_knowledge: list[dict] = Field(default_factory=list)
```

**Update `build_system_prompt()` in prompts.py:**
- Add instance knowledge section after RAG results:
```
--- Community-Validated Answers ---
[1] Q: "How do I install Python?"
    A: "Use `flox install python3`."
    (Upvoted by community)
```

**Test:** In `tests/test_context_engine.py` — verify instance knowledge flows through pipeline.

---

### I9: Smoke Test + Regression

After I1-I8, run full suite:
```bash
PYTHONPATH=support-bot-copilot:support-bot-api:support-bot-shared:support-bot-canon:support-bot-email \
  python3 -m pytest tests/ -q
```

Target: 290+ tests (245 existing + ~45 new from Phase 4).

---

### I10: Commit Phase 4

Single commit:
```
feat: Phase 4 — Intelligence: Codex backend, skill packages, user memory, instance knowledge

- Full Codex LLM backend with code-focused system prompt and tool-use loop
- Multi-signal intent classification with confidence scoring
- Intent-specific prompt variants (code generation, diagnostic, teaching)
- 8 skill packages with SKILL.md, metadata.json, diagnostic prompts
- Manifest inspection for skill detection (package → skill mapping)
- User memory post-interaction updates (recent skills, skill level, projects)
- Instance knowledge with embedding-based similarity search
- Context engine integration for Tier 2 knowledge
- 45+ new tests
```

---

## Execution Order

```
I1 (Codex backend)  ──┐
I2 (intent refine)  ──┤
I3 (prompt variants)──┴── I9 (smoke test) → I10 (commit)
I4 (skill content)  ──┤
I5 (manifest detect)──┤
I6 (user memory)    ──┤
I7 (instance know.) ──┤
I8 (context engine) ──┘
```

I1-I3 are coupled (Codex needs prompts, prompts need intents). I4-I5 are coupled (loader needs content to load). I6-I8 are coupled (memory + instance knowledge → context engine). All three groups are independent of each other.

**Recommended sequence:**
1. I4 (skill content) — no code deps, just content creation
2. I3 (prompt variants) — foundation for I1
3. I1 (Codex backend) — depends on I3
4. I2 (intent classification) — refines routing to I1
5. I5 (manifest inspection) — depends on I4 existing
6. I6 (user memory updates) — standalone
7. I7 + I8 (instance knowledge + context) — coupled pair
8. I9 (smoke test)
9. I10 (commit)

---

## Files Summary

| File | Action |
|------|--------|
| `support-bot-api/src/llm/codex.py` | Rewrite: full Codex backend |
| `support-bot-api/src/llm/prompts.py` | Enhance: intent variants, Codex prompt |
| `support-bot-api/src/router/intent.py` | Enhance: multi-signal scoring |
| `support-bot-api/src/skills/loader.py` | Enhance: manifest inspection, metadata |
| `support-bot-api/src/memory/user.py` | Enhance: post-interaction updates |
| `support-bot-api/src/rag/engine.py` | Enhance: embedding-based instance knowledge |
| `support-bot-api/src/context/engine.py` | Enhance: instance knowledge integration |
| `support-bot-api/src/models/types.py` | Add: instance_knowledge to BuiltContext |
| `support-bot-api/src/main.py` | Wire: memory update post-response |
| `support-bot-api/src/db/models.py` | Add: recent_skills to UserMemory |
| `support-bot-api/alembic/versions/005_*.py` | New: migration for recent_skills |
| `skills/skill-k8s/*` | New: SKILL.md, metadata.json, prompts/ |
| `skills/skill-terraform/*` | New: SKILL.md, metadata.json, prompts/ |
| `skills/skill-aws/*` | New: SKILL.md, metadata.json, prompts/ |
| `skills/skill-gcp/*` | New: SKILL.md, metadata.json, prompts/ |
| `skills/skill-docker/*` | New: SKILL.md, metadata.json, prompts/ |
| `skills/skill-postgres/*` | New: SKILL.md, metadata.json, prompts/ |
| `skills/skill-rust/*` | New: SKILL.md, metadata.json, prompts/ |
| `skills/skill-python/*` | New: SKILL.md, metadata.json, prompts/ |
| `tests/test_codex.py` | New |
| `tests/test_intent_classification.py` | New |
| `tests/test_skill_packages.py` | New |
| `tests/test_user_memory_updates.py` | New |
| `tests/test_instance_knowledge.py` | New |

## Estimated Test Count

- I1 (Codex): ~8 tests
- I2 (intent): ~10 tests (parametrized)
- I3 (prompts): ~6 tests
- I4 (skill packages): ~5 tests (validation)
- I5 (manifest inspection): ~8 tests
- I6 (user memory): ~8 tests
- I7+I8 (instance knowledge): ~6 tests
- **Total new: ~51 tests → ~296 total**
