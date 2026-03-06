"""Context sanitization for event publishing.

Strips secrets, redacts PII, and truncates content before publishing
events to Kafka. Never publish raw user context to the event backbone.
"""

from __future__ import annotations

import base64
import re
from copy import deepcopy
from typing import Any

# Env var keys that indicate secrets
_SECRET_PATTERNS = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|API_KEY|CREDENTIAL|PRIVATE)",
    re.IGNORECASE,
)

# Email pattern
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# IPv4 pattern
_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

# Max text length for event payloads
MAX_TEXT_LENGTH = 2000

# Minimum size (bytes) for base64 blob redaction
_BASE64_MIN_SIZE = 1024


def _is_large_base64(value: str) -> bool:
    """Check if a string looks like a base64 blob larger than 1KB."""
    if len(value) < _BASE64_MIN_SIZE:
        return False
    # Quick heuristic: base64 strings are alphanumeric + /+=
    stripped = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9+/=\s]+", stripped):
        return False
    try:
        decoded = base64.b64decode(stripped, validate=True)
        return len(decoded) >= _BASE64_MIN_SIZE
    except Exception:
        return False


def _redact_manifest_secrets(manifest: str) -> str:
    """Redact values in [vars] sections that look like secrets."""
    lines = manifest.split("\n")
    in_vars = False
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped == "[vars]":
            in_vars = True
            result.append(line)
            continue
        if stripped.startswith("[") and stripped != "[vars]":
            in_vars = False

        if in_vars and "=" in line and _SECRET_PATTERNS.search(line.split("=", 1)[0]):
            key = line.split("=", 1)[0]
            result.append(f"{key}= \"[REDACTED]\"")
        else:
            result.append(line)
    return "\n".join(result)


def sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets, PII, and large blobs from a context dict.

    - Removes env vars matching KEY|SECRET|TOKEN|PASSWORD|API_KEY
    - Redacts base64 blobs > 1KB
    - Scrubs email addresses and IP addresses from free text
    - Redacts [vars] secret values in manifests
    """
    if not context:
        return {}

    result = deepcopy(context)
    _sanitize_recursive(result)
    return result


def _sanitize_recursive(obj: Any, key: str = "") -> None:
    """Recursively sanitize a dict/list structure in-place."""
    if isinstance(obj, dict):
        keys_to_remove = []
        for k, v in obj.items():
            if isinstance(v, str):
                if _SECRET_PATTERNS.search(k):
                    obj[k] = "[REDACTED]"
                elif _is_large_base64(v):
                    obj[k] = "[REDACTED_BASE64]"
                elif k == "manifest":
                    obj[k] = _redact_manifest_secrets(v)
                else:
                    obj[k] = _scrub_pii(v)
            elif isinstance(v, (dict, list)):
                _sanitize_recursive(v, k)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                obj[i] = _scrub_pii(item)
            elif isinstance(item, (dict, list)):
                _sanitize_recursive(item)


def _scrub_pii(text: str) -> str:
    """Remove email addresses and IP addresses from text."""
    text = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = _IPV4_RE.sub("[IP_REDACTED]", text)
    return text


def sanitize_message_for_event(message: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a full message dict for event publishing.

    Truncates content.text first, then sanitizes the whole message.
    """
    if not message:
        return {}

    result = deepcopy(message)

    # Truncate content text before sanitization
    content = result.get("content", {})
    if isinstance(content, dict):
        text = content.get("text", "")
        if isinstance(text, str) and len(text) > MAX_TEXT_LENGTH:
            content["text"] = text[:MAX_TEXT_LENGTH] + "...[truncated]"

    # Now sanitize (strips secrets, PII, base64)
    _sanitize_recursive(result)
    return result
