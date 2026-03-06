"""Test data factories with sensible defaults and overrides."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def make_message(**overrides) -> dict:
    """Create a valid NormalizedMessage dict."""
    msg = {
        "message_id": str(uuid.uuid4()),
        "user_identity": {
            "channel": "cli",
            "channel_user_id": "test_user_1",
            "email": "test@example.com",
            "canonical_user_id": "usr_test1",
            "floxhub_username": "testuser",
            "entitlement_tier": "community",
        },
        "content": {
            "text": "How do I add a package to my Flox environment?",
            "attachments": [],
            "code_blocks": [],
        },
        "context": {
            "project": {
                "has_flox_env": False,
                "manifest": None,
                "detected_skills": [],
            },
            "conversation_id": f"conv_{uuid.uuid4().hex[:12]}",
            "channel_metadata": {},
        },
        "session": {
            "prior_messages": 0,
            "active_skills": [],
            "escalation_attempts": 0,
            "copilot_active": False,
        },
    }
    # Apply overrides (supports nested keys via dot notation-like dicts)
    for key, value in overrides.items():
        if isinstance(value, dict) and key in msg and isinstance(msg[key], dict):
            msg[key].update(value)
        else:
            msg[key] = value
    return msg


def make_vote(**overrides) -> dict:
    """Create a valid Vote dict."""
    vote = {
        "vote_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "conversation_id": f"conv_{uuid.uuid4().hex[:12]}",
        "user_id": "usr_test1",
        "vote": "up",
        "query_text": "How do I install a package?",
        "response_text": "Use `flox install <package>`.",
        "skills_used": ["core-canon"],
        "comment": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    vote.update(overrides)
    return vote


def make_org(**overrides) -> dict:
    """Create a valid Organization dict."""
    org = {
        "name": "Acme Corp",
        "slug": f"acme-{uuid.uuid4().hex[:8]}",
    }
    org.update(overrides)
    return org


def make_org_member(**overrides) -> dict:
    """Create a valid OrgMember dict."""
    member = {
        "org_id": f"org_{uuid.uuid4().hex[:12]}",
        "canonical_user_id": "usr_test1",
        "role": "member",
    }
    member.update(overrides)
    return member


def make_feedback(**overrides) -> dict:
    """Create a valid Feedback dict."""
    fb = {
        "feedback_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "conversation_id": f"conv_{uuid.uuid4().hex[:12]}",
        "user_id": "usr_test1",
        "category": "helpful",
        "detail": "Great explanation, very clear!",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    fb.update(overrides)
    return fb
