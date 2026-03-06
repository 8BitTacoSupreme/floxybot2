#!/usr/bin/env python3
"""Repeatable scraper for flox.dev blog posts and documentation.

Usage:
    python scrape_flox_docs.py                          # Full scrape
    python scrape_flox_docs.py --since 2026-01-01       # Incremental
    python scrape_flox_docs.py --output-dir /tmp/docs   # Custom output

Output is markdown files compatible with ingest_docs.py input.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = os.environ.get("FLOX_ENV_CACHE", "/tmp") + "/scraped_docs"
BLOG_BASE = "https://flox.dev/blog/"
DOCS_BASE = "https://flox.dev/docs/"
REQUEST_DELAY = 1.0  # seconds between requests


def _html_to_markdown(html: str) -> str:
    """Simple HTML-to-markdown conversion without external deps."""
    # Remove script/style
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    # Convert common tags
    text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"# \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"## \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"### \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h4[^>]*>(.*?)</h4>", r"#### \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"```\n\1\n```\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<a[^>]*href=[\"']([^\"']*)[\"'][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.IGNORECASE | re.DOTALL)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Clean whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _fetch_page(url: str, session) -> str | None:
    """Fetch a URL and return HTML content."""
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def _find_links(html: str, base_url: str, prefix: str) -> list[str]:
    """Find all internal links matching the prefix."""
    pattern = re.compile(r'href=["\']([^"\']*)["\']', re.IGNORECASE)
    links = set()
    for match in pattern.finditer(html):
        href = match.group(1)
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean.startswith(prefix) and clean != prefix:
            links.add(clean.rstrip("/"))
    return sorted(links)


def _url_to_filename(url: str, prefix: str) -> str:
    """Convert URL to a safe filename."""
    path = url.replace(prefix, "").strip("/")
    if not path:
        path = "index"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", path) + ".md"


def scrape_section(
    base_url: str,
    output_dir: Path,
    session,
    since: datetime | None = None,
) -> int:
    """Scrape all pages under a base URL and save as markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch index page to discover links
    index_html = _fetch_page(base_url, session)
    if not index_html:
        logger.error("Could not fetch index: %s", base_url)
        return 0

    links = _find_links(index_html, base_url, base_url)
    logger.info("Found %d links under %s", len(links), base_url)

    count = 0
    for url in links:
        filename = _url_to_filename(url, base_url)
        out_path = output_dir / filename

        # Skip if already exists and we're doing incremental
        if since and out_path.exists():
            mtime = datetime.fromtimestamp(out_path.stat().st_mtime)
            if mtime > since:
                logger.info("  Skipping (recent): %s", filename)
                continue

        time.sleep(REQUEST_DELAY)
        html = _fetch_page(url, session)
        if not html:
            continue

        markdown = _html_to_markdown(html)
        if len(markdown.strip()) < 50:
            logger.info("  Skipping (too short): %s", filename)
            continue

        # Prepend source URL as metadata
        header = f"<!-- source: {url} -->\n\n"
        out_path.write_text(header + markdown)
        count += 1
        logger.info("  Saved: %s (%d chars)", filename, len(markdown))

    return count


def main():
    parser = argparse.ArgumentParser(description="Scrape flox.dev blog and docs")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only scrape pages newer than this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--section",
        choices=["blog", "docs", "all"],
        default="all",
        help="Which section to scrape",
    )
    args = parser.parse_args()

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since)

    try:
        import requests
    except ImportError:
        logger.error("requests package required: pip install requests")
        sys.exit(1)

    session = requests.Session()
    session.headers["User-Agent"] = "FloxBot-Canon-Scraper/1.0"

    output_base = Path(args.output_dir)
    total = 0

    if args.section in ("blog", "all"):
        logger.info("Scraping blog posts...")
        total += scrape_section(BLOG_BASE, output_base / "blogs", session, since)

    if args.section in ("docs", "all"):
        logger.info("Scraping documentation...")
        total += scrape_section(DOCS_BASE, output_base / "docs", session, since)

    # Save timestamp for incremental runs
    ts_file = output_base / ".last_scrape"
    ts_file.write_text(datetime.utcnow().isoformat())

    logger.info("Scraping complete. Total pages saved: %d", total)


if __name__ == "__main__":
    main()
