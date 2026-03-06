"""Email → NormalizedMessage normalizer.

Maps SendGrid inbound parse webhook data to the canonical FloxBot message schema.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


def extract_code_blocks(text: str) -> tuple[str, list[str]]:
    """Extract fenced code blocks from text, return (clean_text, blocks)."""
    blocks: list[str] = []
    clean = re.sub(
        r"```(?:\w+)?\n?([\s\S]*?)```",
        lambda m: (blocks.append(m.group(1).strip()) or ""),  # type: ignore[func-returns-value]
        text,
    )
    return clean.strip(), blocks


def make_conversation_id(headers: dict[str, str]) -> str:
    """Derive a conversation ID from email threading headers."""
    # Use In-Reply-To or References for threading, fall back to subject hash
    in_reply_to = headers.get("In-Reply-To", "").strip()
    if in_reply_to:
        return f"email_thread_{hashlib.sha256(in_reply_to.encode()).hexdigest()[:16]}"

    references = headers.get("References", "").strip()
    if references:
        # Use first reference (root message)
        root = references.split()[0]
        return f"email_thread_{hashlib.sha256(root.encode()).hexdigest()[:16]}"

    # No threading headers — use subject as loose grouping
    subject = headers.get("Subject", "").strip()
    # Strip Re:/Fwd: prefixes for grouping
    subject_clean = re.sub(r"^(?:Re|Fwd|FW):\s*", "", subject, flags=re.IGNORECASE)
    return f"email_subject_{hashlib.sha256(subject_clean.encode()).hexdigest()[:16]}"


def normalize_email(form_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a SendGrid inbound parse webhook payload to the canonical schema.

    SendGrid posts multipart form data with fields:
    - from, to, subject, text, html, headers, envelope, attachments, etc.

    Returns a dict matching the NormalizedMessage schema.
    """
    from_email = form_data.get("from", "")
    # Extract bare email from "Name <email>" format
    email_match = re.search(r"<([^>]+)>", from_email)
    sender_email = email_match.group(1) if email_match else from_email.strip()

    subject = form_data.get("subject", "")
    text_body = form_data.get("text", "")
    html_body = form_data.get("html", "")

    # Prefer plain text; fall back to HTML stripped of tags
    body = text_body or re.sub(r"<[^>]+>", "", html_body)

    # Extract code blocks
    clean_text, code_blocks = extract_code_blocks(body)

    # Parse headers for threading
    raw_headers = form_data.get("headers", "")
    headers: dict[str, str] = {}
    if raw_headers:
        for line in raw_headers.split("\n"):
            if ": " in line:
                key, _, value = line.partition(": ")
                headers[key.strip()] = value.strip()
    headers.setdefault("Subject", subject)

    conversation_id = make_conversation_id(headers)

    # Build attachments list
    attachments: list[dict[str, str]] = []
    num_attachments = int(form_data.get("attachments", "0") or "0")
    for i in range(1, num_attachments + 1):
        info = form_data.get(f"attachment-info-{i}")
        if info:
            attachments.append({
                "filename": info.get("filename", f"attachment-{i}"),
                "content_type": info.get("type", "application/octet-stream"),
            })

    # Use sender email hash as stable channel_user_id
    channel_user_id = f"email_{hashlib.sha256(sender_email.lower().encode()).hexdigest()[:16]}"

    return {
        "message_id": hashlib.sha256(
            f"{sender_email}:{subject}:{body[:100]}".encode()
        ).hexdigest()[:32],
        "user_identity": {
            "channel": "email",
            "channel_user_id": channel_user_id,
            "email": sender_email,
        },
        "content": {
            "text": f"[{subject}] {clean_text}" if subject else clean_text,
            "attachments": [
                {"filename": a["filename"], "content_type": a["content_type"]}
                for a in attachments
            ],
            "code_blocks": code_blocks,
        },
        "context": {
            "project": {
                "has_flox_env": False,
                "detected_skills": [],
            },
            "conversation_id": conversation_id,
            "channel_metadata": {
                "subject": subject,
                "from": sender_email,
                "to": form_data.get("to", ""),
            },
        },
        "session": {
            "prior_messages": 0,
            "active_skills": [],
            "escalation_attempts": 0,
            "copilot_active": False,
        },
    }
