"""FloxBot Central API — the brain of the support system."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from .auth.middleware import verify_auth
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
    version="0.1.0",
    description="Multi-channel support system for Flox users",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/message")
async def handle_message(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
):
    """Main message endpoint. All channel adapters hit this.

    Pipeline: auth → entitlement gate → context engine → skill detection →
    intent classification → LLM routing → response
    """
    body = await request.json()

    from .auth.entitlements import resolve_entitlements
    from .context.engine import build_context
    from .memory.conversations import append_to_conversation
    from .router.intent import classify_intent, route_to_backend
    from .skills.loader import detect_and_load_skills

    # Validate input loosely (full Pydantic validation is optional for flexibility)
    if "content" not in body or "text" not in body.get("content", {}):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": "Missing content.text"})

    # 1. Auth + entitlements
    user_identity = body.get("user_identity", {})
    auth_result = await verify_auth(user_identity)
    entitlements = await resolve_entitlements(auth_result, redis_client=redis)

    # 2. Context engine (with DB session for RAG + memory)
    context = await build_context(body, entitlements, session=session)

    # 3. Skill detection + loading (max 2)
    skills = await detect_and_load_skills(context, message=body)

    # 4. Intent classification
    intent = await classify_intent(body, context, skills)

    # 5. Route to LLM backend
    response = await route_to_backend(intent, body, context, skills, entitlements)

    # 6. Save conversation history (async, best-effort)
    conversation_id = body.get("context", {}).get("conversation_id")
    user_id = user_identity.get("canonical_user_id", "anonymous")
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
    publisher=Depends(get_event_publisher),
):
    """Record structured feedback."""
    body = await request.json()

    from .memory.votes import record_feedback

    result = await record_feedback(body, session=session, publisher=publisher)
    return result
