"""FloxBot Central API — the brain of the support system."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth.middleware import verify_auth
from .auth.rate_limiter import check_rate_limit, rate_limit_headers
from .deps import (
    get_db_session,
    get_event_publisher,
    get_redis,
    shutdown,
    startup,
)
from .models.types import Intent

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown lifecycle."""
    await startup()
    yield
    await shutdown()


app = FastAPI(
    title="FloxBot Central API",
    version="0.2.0",
    description="Multi-channel support system for Flox users",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "PUT"],
    allow_headers=["*"],
)


async def _auth_and_rate_limit(request: Request, redis):
    """Shared auth + entitlement + rate limit check. Returns (auth_result, entitlements) or JSONResponse."""
    from .auth.entitlements import resolve_entitlements

    body = await request.json()
    user_identity = body.get("user_identity", {})
    auth_result = await verify_auth(user_identity)
    entitlements = await resolve_entitlements(auth_result, redis_client=redis)

    user_id = auth_result.canonical_user_id or auth_result.floxhub_username or "anonymous"
    allowed, remaining = await check_rate_limit(user_id, entitlements.rate_limit_rpm, redis)

    if not allowed:
        headers = rate_limit_headers(False, 0, entitlements.rate_limit_rpm)
        return None, None, None, JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "retry_after": 60},
            headers=headers,
        )

    return auth_result, entitlements, body, None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/message")
async def handle_message(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
    publisher=Depends(get_event_publisher),
):
    """Main message endpoint. All channel adapters hit this.

    Pipeline: auth → entitlement gate → rate limit → context engine → skill detection →
    intent classification → LLM routing → response
    """
    body = await request.json()

    from .auth.entitlements import resolve_entitlements
    from .context.engine import build_context
    from .events.sanitizer import sanitize_message_for_event
    from .memory.conversations import append_to_conversation
    from .router.intent import classify_intent, route_to_backend
    from .skills.loader import detect_and_load_skills

    # Validate input loosely (full Pydantic validation is optional for flexibility)
    if "content" not in body or "text" not in body.get("content", {}):
        return JSONResponse(status_code=422, content={"detail": "Missing content.text"})

    # 1. Auth + entitlements
    user_identity = body.get("user_identity", {})
    auth_result = await verify_auth(user_identity)
    entitlements = await resolve_entitlements(auth_result, redis_client=redis)

    # 1b. Rate limit
    user_id = auth_result.canonical_user_id or auth_result.floxhub_username or "anonymous"
    allowed, remaining = await check_rate_limit(user_id, entitlements.rate_limit_rpm, redis)
    if not allowed:
        headers = rate_limit_headers(False, 0, entitlements.rate_limit_rpm)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "retry_after": 60},
            headers=headers,
        )

    # 1c. Publish sanitized inbound event (fire-and-forget)
    try:
        sanitized = sanitize_message_for_event(body)
        await publisher.publish("floxbot.messages.inbound", user_id, sanitized)
    except Exception as e:
        logger.warning("Failed to publish inbound event: %s", e)

    # 2. Context engine (with DB session for RAG + memory)
    context = await build_context(body, entitlements, session=session)

    # 3. Skill detection + loading (max 2)
    skills = await detect_and_load_skills(context, message=body, entitlements=entitlements)

    # 4. Intent classification
    intent = await classify_intent(body, context, skills)

    # 4b. Publish context snapshot (fire-and-forget)
    try:
        await publisher.publish("floxbot.context.detected", user_id, {
            "user_id": user_id,
            "skills": [s.get("name", "unknown") if isinstance(s, dict) else str(s) for s in skills],
            "intent": intent.value,
        })
    except Exception as e:
        logger.warning("Failed to publish context event: %s", e)

    # 5. Route to LLM backend
    response = await route_to_backend(intent, body, context, skills, entitlements)

    # 5b. Publish outbound event (fire-and-forget)
    try:
        response_text = response.get("text", "") if isinstance(response, dict) else ""
        truncated = response_text[:2000] if len(response_text) > 2000 else response_text
        await publisher.publish("floxbot.messages.outbound", user_id, {
            "user_id": user_id,
            "response_text": truncated,
            "intent": intent.value,
        })
    except Exception as e:
        logger.warning("Failed to publish outbound event: %s", e)

    # 6. Update user memory (best-effort)
    user_id = user_identity.get("canonical_user_id", "anonymous")
    if user_id != "anonymous":
        try:
            from .memory.user import build_memory_update, update_user_memory
            mem_updates = build_memory_update(response, body, intent.value)
            await update_user_memory(user_id, mem_updates, session=session)
        except Exception as e:
            logger.warning("Failed to update user memory: %s", e)

    # 7. Save conversation history (async, best-effort)
    conversation_id = body.get("context", {}).get("conversation_id")
    if conversation_id:
        try:
            await append_to_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                user_message=body["content"]["text"],
                bot_response=response.get("text", ""),
                session=session,
            )
        except Exception as e:
            logger.warning("Failed to save conversation: %s", e)

    return response


@app.post("/v1/vote")
async def handle_vote(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
    publisher=Depends(get_event_publisher),
):
    """Record a vote on a bot response."""
    body = await request.json()

    from .memory.votes import record_vote

    result = await record_vote(body, session=session, publisher=publisher)
    return result


@app.post("/v1/feedback")
async def handle_feedback(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
    publisher=Depends(get_event_publisher),
):
    """Record structured feedback."""
    body = await request.json()

    from .memory.votes import record_feedback

    result = await record_feedback(body, session=session, publisher=publisher)
    return result


# --- Phase 2: Sync endpoints for Co-Pilot ---


@app.get("/v1/canon/sync")
async def canon_sync(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
):
    """Return canon chunks updated since `since` for delta sync.

    Query params: since (ISO datetime), skills (comma-separated), limit, offset
    """
    from .auth.entitlements import resolve_entitlements

    # Auth check via header
    auth_header = request.headers.get("Authorization", "")
    floxhub_username = None
    if auth_header.startswith("Bearer "):
        # In production this would validate the token; for now accept as username
        floxhub_username = auth_header.split(" ", 1)[1]

    from .auth.middleware import verify_auth
    auth_result = await verify_auth({"floxhub_username": floxhub_username} if floxhub_username else {})
    entitlements = await resolve_entitlements(auth_result, redis_client=redis)

    since_str = request.query_params.get("since", "2000-01-01T00:00:00Z")
    skills_csv = request.query_params.get("skills", "")
    limit = int(request.query_params.get("limit", "100"))
    offset = int(request.query_params.get("offset", "0"))

    from .db.models import CanonChunk
    since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))

    stmt = select(CanonChunk).where(CanonChunk.updated_at >= since)
    if skills_csv:
        skill_list = [s.strip() for s in skills_csv.split(",") if s.strip()]
        if skill_list:
            stmt = stmt.where(CanonChunk.skill_name.in_(skill_list))
    stmt = stmt.order_by(CanonChunk.updated_at).offset(offset).limit(limit)

    result = await session.execute(stmt)
    chunks = result.scalars().all()

    return {
        "chunks": [
            {
                "id": str(c.id),
                "skill_name": c.skill_name,
                "heading": c.heading_hierarchy,
                "content": c.content,
                "content_hash": c.content_hash,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in chunks
        ],
        "count": len(chunks),
        "offset": offset,
        "limit": limit,
    }


@app.get("/v1/memory/{user_id}")
async def get_memory(
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
):
    """Fetch user memory."""
    from .memory.user import get_user_memory

    memory = await get_user_memory(user_id, session=session)
    return {"user_id": user_id, "memory": memory}


@app.put("/v1/memory/{user_id}")
async def update_memory(
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
):
    """Update user memory."""
    body = await request.json()
    from .memory.user import update_user_memory

    await update_user_memory(user_id, body, session=session)
    return {"status": "ok", "user_id": user_id}


@app.post("/v1/votes/batch")
async def batch_votes(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
    publisher=Depends(get_event_publisher),
):
    """Accept an array of votes from Co-Pilot queue flush."""
    body = await request.json()

    from .memory.votes import record_vote

    votes = body if isinstance(body, list) else body.get("votes", [])
    results = []
    for vote_data in votes:
        r = await record_vote(vote_data, session=session, publisher=publisher)
        results.append(r)
    return {"status": "ok", "count": len(results), "results": results}


@app.post("/v1/tickets")
async def create_ticket_endpoint(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
    publisher=Depends(get_event_publisher),
):
    """Create a triaged support ticket."""
    body = await request.json()

    from .memory.tickets import create_ticket

    result = await create_ticket(body, session=session, publisher=publisher)
    return result


@app.get("/v1/entitlements")
async def get_entitlements(
    request: Request,
    redis=Depends(get_redis),
):
    """Resolve and return entitlements for the auth header."""
    from .auth.entitlements import resolve_entitlements

    auth_header = request.headers.get("Authorization", "")
    floxhub_username = None
    if auth_header.startswith("Bearer "):
        floxhub_username = auth_header.split(" ", 1)[1]

    auth_result = await verify_auth({"floxhub_username": floxhub_username} if floxhub_username else {})
    entitlements = await resolve_entitlements(auth_result, redis_client=redis)
    return entitlements.model_dump()


@app.post("/v1/telemetry")
async def handle_telemetry(
    request: Request,
    publisher=Depends(get_event_publisher),
):
    """Accept a batch of telemetry events from Co-Pilot and publish to Kafka."""
    body = await request.json()
    events = body if isinstance(body, list) else body.get("events", [])

    for event in events:
        try:
            user_id = event.get("user_id", "anonymous")
            await publisher.publish("floxbot.copilot.telemetry", user_id, event)
        except Exception as e:
            logger.warning("Failed to publish telemetry event: %s", e)

    return {"status": "ok", "count": len(events)}


# --- Phase 6: Admin Dashboard API ---


@app.get("/v1/admin/org/{org_id}/stats")
async def admin_org_stats(
    org_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
):
    """Get org-scoped usage stats. Enterprise auth gate."""
    from .auth.entitlements import resolve_entitlements
    from .admin.org_stats import get_org_stats

    auth_header = request.headers.get("Authorization", "")
    floxhub_username = None
    if auth_header.startswith("Bearer "):
        floxhub_username = auth_header.split(" ", 1)[1]

    auth_result = await verify_auth({"floxhub_username": floxhub_username} if floxhub_username else {})
    entitlements = await resolve_entitlements(auth_result, redis_client=redis)

    if "admin_dashboard" not in entitlements.features:
        return JSONResponse(status_code=403, content={"detail": "Enterprise feature required"})

    stats = await get_org_stats(org_id, session)
    return stats


@app.get("/v1/admin/org/{org_id}/members")
async def admin_org_members(
    org_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
):
    """Get org members. Enterprise auth gate."""
    from .auth.entitlements import resolve_entitlements
    from .admin.org_stats import get_org_members

    auth_header = request.headers.get("Authorization", "")
    floxhub_username = None
    if auth_header.startswith("Bearer "):
        floxhub_username = auth_header.split(" ", 1)[1]

    auth_result = await verify_auth({"floxhub_username": floxhub_username} if floxhub_username else {})
    entitlements = await resolve_entitlements(auth_result, redis_client=redis)

    if "admin_dashboard" not in entitlements.features:
        return JSONResponse(status_code=403, content={"detail": "Enterprise feature required"})

    members = await get_org_members(org_id, session)
    return {"org_id": org_id, "members": members}
