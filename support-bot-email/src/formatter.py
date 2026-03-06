"""Format API responses as email replies.

Converts the Central API's markdown response into an HTML email body
suitable for sending via SendGrid.
"""

from __future__ import annotations

import re


def markdown_to_html(text: str) -> str:
    """Minimal markdown → HTML conversion for email replies."""
    # Code blocks
    text = re.sub(
        r"```(\w+)?\n([\s\S]*?)```",
        r'<pre style="background:#f4f4f4;padding:12px;border-radius:4px;'
        r'font-family:monospace;font-size:13px;overflow-x:auto">\2</pre>',
        text,
    )
    # Inline code
    text = re.sub(
        r"`([^`]+)`",
        r'<code style="background:#f4f4f4;padding:2px 4px;border-radius:3px;'
        r'font-family:monospace;font-size:13px">\1</code>',
        text,
    )
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Headers
    text = re.sub(r"^### (.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)
    # Line breaks (but not inside <pre> blocks)
    text = re.sub(r"\n(?!<)", "<br>\n", text)
    return text


def format_reply(
    response_text: str,
    original_subject: str,
    sources: list[str] | None = None,
) -> dict[str, str]:
    """Format an API response as a SendGrid reply email.

    Returns dict with 'subject' and 'html' keys.
    """
    html_body = markdown_to_html(response_text)

    if sources:
        source_links = "".join(f"<li>{s}</li>" for s in sources)
        html_body += (
            '<hr style="margin-top:16px">'
            '<p style="font-size:12px;color:#666">Sources:</p>'
            f'<ul style="font-size:12px;color:#666">{source_links}</ul>'
        )

    html_body += (
        '<p style="font-size:11px;color:#999;margin-top:24px">'
        "— FloxBot Support</p>"
    )

    subject = original_subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    return {
        "subject": subject,
        "html": html_body,
    }
