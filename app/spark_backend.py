"""Forward marketing data to Spark via POST /api/site/lead (unified ingest). See Spark docs/SPARKS_SITE_BACKEND.md."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger(__name__)


def enabled() -> bool:
    base = (os.getenv("SPARK_BACKEND_URL") or "").strip()
    secret = (os.getenv("SPARK_SITE_INGEST_SECRET") or "").strip()
    return bool(base and secret)


def _base() -> str:
    return (os.getenv("SPARK_BACKEND_URL") or "").strip().rstrip("/")


def _secret() -> str:
    return (os.getenv("SPARK_SITE_INGEST_SECRET") or "").strip()


def _headers() -> dict[str, str]:
    return {
        "X-Spark-Site-Secret": _secret(),
        "Content-Type": "application/json",
    }


def post_site_lead(payload: dict, *, timeout: float = 25) -> tuple[bool, dict | None]:
    """
    POST canonical Spark ingest: /api/site/lead (Spark routes nurture vs scan attach from the JSON).
    """
    try:
        import requests
    except ImportError:
        _log.warning("spark_backend: requests missing")
        return False, None
    try:
        r = requests.post(
            f"{_base()}/api/site/lead",
            json=payload,
            headers=_headers(),
            timeout=timeout,
        )
        if r.status_code not in (200, 201):
            _log.warning("spark_backend site-lead: HTTP %s %s", r.status_code, (r.text or "")[:300])
            return False, None
        try:
            return True, r.json()
        except Exception:
            return True, None
    except Exception as e:
        _log.warning("spark_backend site-lead: %s", e)
        return False, None


def post_form_lead(
    *,
    fname: str,
    email: str,
    submission_type: str,
    resource_slug: str | None = None,
    business_stage: str | None = None,
    website_url: str | None = None,
    lead_origin: str | None = None,
) -> bool:
    payload = {
        "fname": fname,
        "email": email,
        "submission_type": submission_type,
        "resource_slug": resource_slug,
        "business_stage": business_stage,
        "website_url": website_url,
    }
    if lead_origin:
        payload["lead_origin"] = lead_origin
    ok, _ = post_site_lead(payload, timeout=25)
    return ok


def store_cro_scan_report(*, report: dict, store_url: str, store_name: str | None) -> str | None:
    """Returns secret token for /cro-scan/report/<token> on Sparksmetrics."""
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.post(
            f"{_base()}/api/site/cro-scan/report",
            json={"report": report, "store_url": store_url, "store_name": store_name},
            headers=_headers(),
            timeout=60,
        )
        if r.status_code not in (200, 201):
            _log.warning("spark_backend cro-scan report: HTTP %s %s", r.status_code, (r.text or "")[:300])
            return None
        data = r.json()
        return (data.get("token") or "").strip() or None
    except Exception as e:
        _log.warning("spark_backend cro-scan report: %s", e)
        return None


def fetch_cro_scan_report_json(token: str) -> dict[str, Any] | None:
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.get(
            f"{_base()}/api/site/cro-scan/report-by-token/{token}",
            headers=_headers(),
            timeout=25,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        raw = data.get("report_json")
        if isinstance(raw, str):
            return json.loads(raw)
        return None
    except Exception as e:
        _log.warning("spark_backend fetch report: %s", e)
        return None


def register_nurture_cro_scan(
    *, email: str, store_url: str, fname: str, orders_per_month: str | None
) -> int | None:
    payload: dict[str, Any] = {
        "email": email,
        "store_url": store_url,
        "fname": fname,
        "orders_per_month": orders_per_month,
        "submission_type": "cro_scan",
        "lead_origin": "sparksmetrics.com",
    }
    ok, data = post_site_lead(payload, timeout=25)
    if not ok or not data:
        _log.warning("spark_backend nurture register: failed or empty response")
        return None
    # Unified ingest returns nurture_lead_id; legacy Spark alias returned lead_id
    lid = data.get("nurture_lead_id")
    if lid is None:
        lid = data.get("lead_id")
    try:
        return int(lid) if lid is not None else None
    except (TypeError, ValueError):
        return None


def attach_nurture_scan(*, email: str, store_url: str, report: dict) -> bool:
    ok, _ = post_site_lead(
        {
            "email": email,
            "store_url": store_url,
            "report": report,
        },
        timeout=120,
    )
    if not ok:
        _log.warning("spark_backend attach-scan (site-lead): failed")
    return ok


def trigger_nurture_cron_on_spark() -> bool:
    """POST Spark /cro-nurture/api/cron/run (enrich + dispatch)."""
    cron_tok = (os.getenv("SPARK_CRO_NURTURE_CRON_TOKEN") or os.getenv("CRO_NURTURE_CRON_TOKEN") or "").strip()
    if not cron_tok:
        _log.warning("spark_backend cron: set SPARK_CRO_NURTURE_CRON_TOKEN (same value as on Spark)")
        return False
    try:
        import requests
    except ImportError:
        return False
    try:
        r = requests.post(
            f"{_base()}/cro-nurture/api/cron/run",
            params={"token": cron_tok},
            timeout=120,
        )
        if r.status_code != 200:
            _log.warning("spark_backend cron: HTTP %s %s", r.status_code, (r.text or "")[:300])
            return False
        return True
    except Exception as e:
        _log.warning("spark_backend cron: %s", e)
        return False
