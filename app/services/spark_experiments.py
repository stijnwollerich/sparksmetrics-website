"""Load Spark experiments for the public website (filter rules live here)."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

from flask import url_for

from app import spark_backend

_log = logging.getLogger(__name__)

_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])
_CACHE_TTL = 300

_STAT_KEYS = (
    "conv_improvement",
    "psv_improvement",
    "aov_improvement",
    "rev_added",
    "testing_users_count",
)


def _experiment_image_url(path: str | None, *, w: int = 640, h: int = 480) -> str | None:
    if not path:
        return None
    q = urlencode({"path": path, "w": w, "h": h, "q": 80})
    return url_for("main.spark_experiment_image", _external=False) + "?" + q


def _has_before_after_images(raw: dict[str, Any]) -> bool:
    ctrl = raw.get("control") if isinstance(raw.get("control"), dict) else {}
    chal = raw.get("challenger") if isinstance(raw.get("challenger"), dict) else {}
    return bool(ctrl.get("image_path") and chal.get("image_path"))


def _has_marked_winner(raw: dict[str, Any]) -> bool:
    if raw.get("successful") is True:
        return True
    for key in ("control", "challenger"):
        arm = raw.get(key)
        if isinstance(arm, dict) and arm.get("is_winner"):
            return True
    return bool(raw.get("winner_name"))


def _has_performance_stats(raw: dict[str, Any]) -> bool:
    return any(raw.get(k) is not None for k in _STAT_KEYS)


def _eligible_for_website_display(raw: dict[str, Any]) -> bool:
    """Winning test with performance stats and before/after images (no manual publish gate)."""
    return (
        _has_before_after_images(raw)
        and _has_marked_winner(raw)
        and _has_performance_stats(raw)
    )


def _enrich_experiment(raw: dict[str, Any]) -> dict[str, Any]:
    exp = dict(raw)
    for key in ("control", "challenger"):
        arm = exp.get(key)
        if not isinstance(arm, dict):
            continue
        arm = dict(arm)
        arm["image_url"] = _experiment_image_url(arm.get("image_path"), w=560, h=700)
        exp[key] = arm
    exp["result_image_urls"] = [
        u
        for p in (exp.get("result_image_paths") or [])
        if (u := _experiment_image_url(p, w=900, h=600))
    ]
    return exp


def get_website_experiments(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    global _cache
    if not spark_backend.enabled():
        return []
    now = time.time()
    cached_at, cached = _cache
    if not force_refresh and cached and (now - cached_at) < _CACHE_TTL:
        return cached
    rows = spark_backend.fetch_website_experiments()
    eligible = [r for r in rows if isinstance(r, dict) and _eligible_for_website_display(r)]
    enriched = [_enrich_experiment(r) for r in eligible]
    _cache = (now, enriched)
    return enriched
