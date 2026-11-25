"""Video companion pages (/videos/<slug>): one JSON file per long YouTube video.

Two folders, merged:
- app/video_pages/       pages committed to git (hand-checked or seeded locally)
- instance/video_pages/  pages written by tasks/video_autopilot.py on the server (gitignored,
                         so a deploy never conflicts with them). Same youtube_id in both: instance wins.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

from markupsafe import Markup, escape

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "app" / "video_pages"
AUTO_DIR = ROOT / "instance" / "video_pages"

_cache: dict = {"at": 0.0, "pages": []}
_CACHE_SECONDS = 60


def slugify(text: str, max_len: int = 70) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    return text or "video"


def _read_dir(folder: Path) -> list[dict]:
    pages = []
    if not folder.is_dir():
        return pages
    for path in sorted(folder.glob("*.json")):
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if page.get("slug") and page.get("youtube_id") and page.get("title"):
            pages.append(page)
    return pages


def load_video_pages(fresh: bool = False) -> list[dict]:
    """All pages, newest first. Cached for a minute so the autopilot's new files show up without a restart."""
    if not fresh and time.time() - _cache["at"] < _CACHE_SECONDS:
        return _cache["pages"]
    by_id: dict[str, dict] = {}
    for page in _read_dir(SEED_DIR) + _read_dir(AUTO_DIR):
        by_id[page["youtube_id"]] = page
    pages = sorted(by_id.values(), key=lambda p: p.get("published") or "", reverse=True)
    _cache.update(at=time.time(), pages=pages)
    return pages


def get_video_page(slug: str) -> dict | None:
    return next((p for p in load_video_pages() if p["slug"] == slug), None)


def related_pages(page: dict, limit: int = 3) -> list[dict]:
    tags = set(page.get("tags") or [])
    others = [p for p in load_video_pages() if p["youtube_id"] != page["youtube_id"]]
    others.sort(key=lambda p: (len(tags & set(p.get("tags") or [])), p.get("published") or ""), reverse=True)
    return others[:limit]


def timestamp(seconds: int | None) -> str:
    s = int(seconds or 0)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def iso_duration(seconds: int | None) -> str:
    s = int(seconds or 0)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"PT{h}H{m}M{sec}S" if h else f"PT{m}M{sec}S"


def rich(text: str) -> Markup:
    """Escape, then turn **x** into <strong>x</strong>. Content is generated, so nothing else is trusted."""
    safe = str(escape(text or ""))
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe))


def plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
