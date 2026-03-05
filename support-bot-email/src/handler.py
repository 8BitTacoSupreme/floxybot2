"""FloxBot Email Adapter — SendGrid inbound parse webhook.

Normalizes inbound emails to the canonical format and forwards to Central API.

TODO: Implement:
- SendGrid inbound parse webhook endpoint
- Email parsing (subject, body, attachments, code blocks)
- Normalize to canonical message format
- POST /v1/message
- Format response as reply email via SendGrid
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
