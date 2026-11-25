"""A/B test case studies (/ab-tests/<slug>): one JSON file + anonymised images per winning Spark experiment.

Same two-folder setup as app/video_pages.py:
- app/case_studies/       committed (seeded locally), images in app/case_studies/images/
- instance/case_studies/  written by tasks/case_study_autopilot.py on the server (gitignored)

Pages only ever show replica (anonymised) images and never the client name or domain: the autopilot
checks both before it writes a file, and nothing else feeds these pages.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "app" / "case_studies"
AUTO_DIR = ROOT / "instance" / "case_studies"

_cache: dict = {"at": 0.0, "items": []}
_CACHE_SECONDS = 60


def _read_dir(folder: Path) -> list[dict]:
    items = []
    if not folder.is_dir():
        return items
    for path in sorted(folder.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if item.get("slug") and item.get("experiment_id") and item.get("images", {}).get("control") and item.get("images", {}).get("winner"):
            items.append(item)
    return items


def load_case_studies(fresh: bool = False) -> list[dict]:
    """All case studies, most recent test first. Server copy wins over the committed one."""
    if not fresh and time.time() - _cache["at"] < _CACHE_SECONDS:
        return _cache["items"]
    by_id: dict[int, dict] = {}
    for item in _read_dir(SEED_DIR) + _read_dir(AUTO_DIR):
        by_id[int(item["experiment_id"])] = item
    items = sorted(by_id.values(), key=lambda c: c.get("end_date") or "", reverse=True)
    _cache.update(at=time.time(), items=items)
    return items


def get_case_study(slug: str) -> dict | None:
    return next((c for c in load_case_studies() if c["slug"] == slug), None)


def image_file(name: str) -> Path | None:
    """Resolve an image name to a file in either images folder (no path traversal)."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    for folder in (AUTO_DIR / "images", SEED_DIR / "images"):
        path = folder / name
        if path.is_file():
            return path
    return None


def related_case_studies(item: dict, limit: int = 3) -> list[dict]:
    others = [c for c in load_case_studies() if c["experiment_id"] != item["experiment_id"]]
    others.sort(key=lambda c: (c.get("page_type") == item.get("page_type"), c.get("end_date") or ""), reverse=True)
    return others[:limit]


def as_gallery_card(item: dict, image_url) -> dict:
    """Shape the existing experiment card templates expect (_experiment_*.html)."""
    r = item.get("results") or {}
    return {
        "test_name": item.get("card_title") or item["title"],
        "page": item.get("page_type"),
        "conv_improvement": r.get("conv_improvement"),
        "psv_improvement": r.get("psv_improvement"),
        "aov_improvement": r.get("aov_improvement"),
        "rev_added": r.get("rev_added"),
        "rev_added_3m": r.get("rev_added_3m"),
        "control": {"image_url": image_url(item["images"]["control"])},
        "challenger": {"image_url": image_url(item["images"]["winner"]), "is_winner": True},
        "url": item.get("url"),
        "slug": item["slug"],
    }
