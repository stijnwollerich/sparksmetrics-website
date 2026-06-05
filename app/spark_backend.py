"""Forward marketing data to Spark via POST /api/site/lead (unified ingest).

Spark app: see Spark `docs/SPARKS_SITE_BACKEND.md`. Payload field reference for this repo: `docs/SPARK_SITE_LEAD_API.md`.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger(__name__)


def _enroll_nurture_for_submission_type(submission_type: str) -> bool:
    """True if this submission_type should request nurture automation on Spark (see SPARK_NURTURE_ENROLLMENT_TYPES)."""
    st = (submission_type or "").strip().lower()
    if not st:
        return False
    try:
        from flask import has_app_context, current_app

        if has_app_context() and current_app.config.get("SPARK_NURTURE_ENROLLMENT_TYPES") is not None:
            return st in current_app.config["SPARK_NURTURE_ENROLLMENT_TYPES"]
    except Exception:
        pass
    from app.config import get_spark_nurture_enrollment_types

    return st in get_spark_nurture_enrollment_types()


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
    form_page_url: str | None = None,
    orders_per_month: str | None = None,
    conversion_rate: str | None = None,
    average_order_value: str | None = None,
    enroll_nurture_override: bool | None = None,
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
    if (form_page_url or "").strip():
        payload["form_page_url"] = form_page_url.strip()
    if (orders_per_month or "").strip():
        payload["orders_per_month"] = orders_per_month.strip()
    if (conversion_rate or "").strip():
        payload["conversion_rate"] = conversion_rate.strip()
    if (average_order_value or "").strip():
        payload["average_order_value"] = average_order_value.strip()
    enroll = _enroll_nurture_for_submission_type(submission_type)
    # CRO cost/ROI: default lead-gen on Spark (like /cro-scan). Set SPARK_CRO_COST_ROI_ENROLL_NURTURE=0 to disable.
    # Spark should branch nurture/copy by submission_type so this is not the CRO scan drip.
    st = (submission_type or "").strip().lower()
    if st == "cro_cost_roi":
        raw = (os.getenv("SPARK_CRO_COST_ROI_ENROLL_NURTURE") or "1").strip().lower()
        enroll = raw not in ("0", "false", "no", "off")
    if enroll_nurture_override is not None:
        enroll = enroll_nurture_override
    payload["enroll_nurture"] = enroll
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
    *,
    email: str,
    store_url: str,
    fname: str,
    orders_per_month: str | None,
    form_page_url: str | None = None,
) -> int | None:
    payload: dict[str, Any] = {
        "email": email,
        "store_url": store_url,
        "fname": fname,
        "orders_per_month": orders_per_month,
        "submission_type": "cro_scan",
        "lead_origin": "sparksmetrics.com",
    }
    if (form_page_url or "").strip():
        payload["form_page_url"] = form_page_url.strip()
    payload["enroll_nurture"] = _enroll_nurture_for_submission_type("cro_scan")
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


def attach_nurture_scan(
    *,
    email: str,
    store_url: str,
    report: dict,
    submission_type: str = "cro_scan",
    report_view_url: str | None = None,
) -> bool:
    st = (submission_type or "cro_scan").strip().lower() or "cro_scan"
    payload: dict[str, Any] = {
        "email": email,
        "store_url": store_url,
        "report": report,
        "submission_type": st,
        "enroll_nurture": _enroll_nurture_for_submission_type(st),
    }
    if (report_view_url or "").strip():
        payload["report_view_url"] = report_view_url.strip()
    ok, _ = post_site_lead(payload, timeout=120)
    if not ok:
        _log.warning("spark_backend attach-scan (site-lead): failed")
    return ok


def trigger_cro_scan_run(
    *,
    store_url: str,
    email: str,
    fname: str,
    delivery_mode: str = "funnel",
    spark_attach_submission_type: str = "cro_scan",
) -> bool:
    """POST Spark ``/api/site/cro-scan/run`` (202). Scan runs on Spark."""
    try:
        import requests
    except ImportError:
        return False
    try:
        r = requests.post(
            f"{_base()}/api/site/cro-scan/run",
            json={
                "store_url": store_url,
                "email": email,
                "fname": fname,
                "delivery_mode": delivery_mode,
                "submission_type": spark_attach_submission_type,
            },
            headers=_headers(),
            timeout=8,
        )
        if r.status_code not in (200, 202):
            _log.warning("spark_backend cro-scan run: HTTP %s %s", r.status_code, (r.text or "")[:300])
            return False
        return True
    except Exception as e:
        _log.warning("spark_backend cro-scan run: %s", e)
        return False


def check_cro_store(*, website_url: str) -> dict | None:
    """POST Spark ``/api/site/cro-scan/check-store`` → JSON or None on failure."""
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.post(
            f"{_base()}/api/site/cro-scan/check-store",
            json={"website_url": website_url},
            headers=_headers(),
            timeout=120,
        )
        if r.status_code != 200:
            _log.warning("spark_backend check-store: HTTP %s %s", r.status_code, (r.text or "")[:300])
            return None
        return r.json()
    except Exception as e:
        _log.warning("spark_backend check-store: %s", e)
        return None


def fetch_website_experiments() -> list[dict[str, Any]]:
    """GET Spark /api/site/experiments — all experiments; marketing app filters locally."""
    try:
        import requests
    except ImportError:
        return []
    try:
        r = requests.get(
            f"{_base()}/api/site/experiments",
            headers=_headers(),
            timeout=25,
        )
        if r.status_code != 200:
            _log.warning("spark_backend experiments: HTTP %s %s", r.status_code, (r.text or "")[:300])
            return []
        data = r.json()
        rows = data.get("experiments")
        return rows if isinstance(rows, list) else []
    except Exception as e:
        _log.warning("spark_backend experiments: %s", e)
        return []


def fetch_experiment_image(*, params: dict[str, str]) -> tuple[int, bytes | None, str | None]:
    """GET Spark /api/site/experiments/image. Returns (status, body, content_type)."""
    try:
        import requests
    except ImportError:
        return 0, None, None
    try:
        r = requests.get(
            f"{_base()}/api/site/experiments/image",
            params=params,
            headers=_headers(),
            timeout=20,
        )
        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip() or None
        return r.status_code, r.content, ct
    except Exception as e:
        _log.warning("spark_backend experiment image: %s", e)
        return 0, None, None


def fetch_cro_preview_image(*, params: dict[str, str]) -> tuple[int, bytes | None]:
    """GET Spark preview-image (secret). Returns (status_code, body or None)."""
    try:
        import requests
    except ImportError:
        return 0, None
    try:
        r = requests.get(
            f"{_base()}/api/site/cro-scan/preview-image",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        return r.status_code, r.content
    except Exception as e:
        _log.warning("spark_backend preview-image: %s", e)
        return 0, None


def post_cro_test_discovery(*, url: str, fast: bool = False) -> dict | None:
    """POST Spark test-discovery JSON."""
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.post(
            f"{_base()}/api/site/cro-scan/test-discovery",
            json={"url": url, "fast": fast},
            headers=_headers(),
            timeout=120,
        )
        if r.status_code not in (200, 500):
            _log.warning("spark_backend test-discovery: HTTP %s", r.status_code)
            return None
        return r.json()
    except Exception as e:
        _log.warning("spark_backend test-discovery: %s", e)
        return None


def trigger_nurture_cron_on_spark() -> bool:
    """POST Spark /cro-nurture/api/cron/run (enrich + dispatch)."""
    # Align with Spark cn_config.cron_token() lookup (EMAIL_AUTOMATION_CRON_TOKEN / CRO_NURTURE_CRON_TOKEN / …).
    cron_tok = (
        (os.getenv("EMAIL_AUTOMATION_CRON_TOKEN") or "").strip()
        or (os.getenv("SPARK_EMAIL_AUTOMATION_CRON_TOKEN") or "").strip()
        or (os.getenv("CRO_NURTURE_CRON_TOKEN") or "").strip()
        or (os.getenv("SPARK_CRO_NURTURE_CRON_TOKEN") or "").strip()
    )
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
