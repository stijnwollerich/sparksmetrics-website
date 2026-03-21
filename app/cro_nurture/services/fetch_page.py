"""Fetch public HTML and extract visible text (no third-party crawl APIs)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.cro_nurture.services import config as cn_config


def normalize_site_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("site_url is required")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError("invalid site_url")
    return parsed._replace(fragment="").geturl()


def fetch_visible_text(url: str) -> tuple[str, dict]:
    timeout = cn_config.fetch_timeout_seconds()
    max_bytes = cn_config.fetch_max_bytes()
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CRO-Nurture/1.0; +https://sparksmetrics.com)",
        "Accept": "text/html,application/xhtml+xml",
    }
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
    resp.raise_for_status()
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "html" not in ctype and "text" not in ctype:
        raise ValueError(f"unexpected content-type: {ctype}")

    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            break
        chunks.append(chunk)
    raw_bytes = b"".join(chunks)
    html = raw_bytes.decode(resp.encoding or "utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    final_url = resp.url
    return text[:120_000], {"title": title[:500], "final_url": final_url}
