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

_LIFT_KEYS = (
    "conv_improvement",
    "psv_improvement",
    "aov_improvement",
    "rev_added",
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


def _arm_is_winner(raw: dict[str, Any], arm_key: str) -> bool:
    arm = raw.get(arm_key)
    return isinstance(arm, dict) and bool(arm.get("is_winner"))


def _has_positive_lift(raw: dict[str, Any]) -> bool:
    for key in _LIFT_KEYS:
        val = raw.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return True
    return False


def _has_marked_winner(raw: dict[str, Any]) -> bool:
    """Only show tests where the variant won — never control or inconclusive losses."""
    if _arm_is_winner(raw, "control"):
        return False
    if _arm_is_winner(raw, "challenger"):
        return True
    # Fallback when Spark only sends winner_name: require a positive lift so
    # completed-but-losing tests (negative conv_improvement) stay hidden.
    if raw.get("winner_name"):
        return _has_positive_lift(raw)
    return False


def _eligible_for_website_display(raw: dict[str, Any]) -> bool:
    """Winning variant with positive lift and before/after images."""
    return (
        _has_before_after_images(raw)
        and _has_marked_winner(raw)
        and _has_positive_lift(raw)
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
