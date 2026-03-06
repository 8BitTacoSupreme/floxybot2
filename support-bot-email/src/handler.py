"""FloxBot Email Adapter — SendGrid inbound parse webhook.

Receives inbound emails via SendGrid, normalizes to canonical format,
forwards to Central API, and sends reply via SendGrid.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

import httpx
from fastapi import FastAPI, Form, Request, Response

from .formatter import format_reply
from .normalizer import normalize_email

logger = logging.getLogger(__name__)

app = FastAPI(title="FloxBot Email Adapter")

FLOXBOT_API_URL = os.environ.get("FLOXBOT_API_URL", "http://localhost:8000")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
WEBHOOK_SECRET = os.environ.get("FLOXBOT_WEBHOOK_SECRET", "")


@app.get("/health")
async def health():
    return {"status": "ok", "adapter": "email"}


@app.post("/webhook")
async def inbound_email(request: Request):
    """Handle SendGrid inbound parse webhook.

    SendGrid posts multipart/form-data with email fields.
    """
    form_data = await request.form()
    form_dict = {k: v for k, v in form_data.items()}

    # Verify webhook signature if secret is configured
    if WEBHOOK_SECRET:
        signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")
        payload = timestamp + str(form_dict)
        expected = hmac.new(
            WEBHOOK_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("Invalid webhook signature")
            return Response(status_code=403)

    # Normalize email to canonical format
    normalized = normalize_email(form_dict)

    logger.info(
        "Received email from %s: %s",
        normalized["user_identity"]["email"],
        form_dict.get("subject", "(no subject)"),
    )

    # Forward to Central API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{FLOXBOT_API_URL}/v1/message",
                json=normalized,
            )
            resp.raise_for_status()
            api_response = resp.json()
    except Exception as e:
        logger.error("Failed to call Central API: %s", e)
        return {"status": "error", "detail": str(e)}

    # Format and send reply email
    response_text = api_response.get("response", {}).get("text", "")
    sources = api_response.get("response", {}).get("sources", [])
    original_subject = form_dict.get("subject", "")

    if response_text and SENDGRID_API_KEY:
        reply = format_reply(response_text, original_subject, sources)
        sender_email = normalized["user_identity"]["email"]
        await _send_reply(sender_email, reply)

    return {"status": "ok"}


async def _send_reply(to_email: str, reply: dict[str, str]) -> None:
    """Send a reply email via SendGrid."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": "support@flox.dev", "name": "FloxBot"},
                    "subject": reply["subject"],
                    "content": [{"type": "text/html", "value": reply["html"]}],
                },
            )
    except Exception as e:
        logger.error("Failed to send reply email: %s", e)
