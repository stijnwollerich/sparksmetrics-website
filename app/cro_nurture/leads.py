"""Create / update nurture leads from the CRO scan funnel (server-side, no HTTP ingest required)."""

from __future__ import annotations

import copy
import os
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from app.models import db
from app.cro_nurture.lead_flags import NURTURE_INSTANT_TEST_KEY, lead_skip_sequence_delays
from app.cro_nurture.scan_schedule import first_send_delay_seconds_from_sequence, step1_email_already_sent
from app.cro_nurture.sequence_schedule import ensure_default_sequence_from_schedule
from app.cro_nurture.models import CroNurtureEmailSend, CroNurtureLead, CroNurtureSequence
from app.cro_nurture.services import config as cn_config
from app.cro_nurture.services.brevo_send import upsert_contact
from app.cro_nurture.services.fetch_page import normalize_site_url


def _strip_heavy_report(report: dict[str, Any]) -> dict[str, Any]:
    """Remove embedded screenshot data URIs (large) before storing on lead."""
    r = copy.deepcopy(report)
    pages = r.get("pages")
    if isinstance(pages, dict):
        for _k, page in pages.items():
            if isinstance(page, dict) and "screenshot_data_uri" in page:
                page.pop("screenshot_data_uri", None)
    return r


def _persist_nurture_lead(
    *,
    email: str,
    site_url: str,
    first_name: str | None,
    last_name: str | None,
    cro_payload: dict[str, Any] | None,
    source_tag: str,
) -> CroNurtureLead | None:
    ensure_default_sequence_from_schedule()
    seq = CroNurtureSequence.query.filter_by(is_active=True).order_by(CroNurtureSequence.id.asc()).first()
    if not seq:
        return None
    lead = CroNurtureLead(
        email=email,
        first_name=first_name,
        last_name=last_name,
        site_url=site_url,
        cro_scan_payload=cro_payload,
        enrichment_status="pending",
        sequence_id=seq.id,
        next_step_order=1,
        next_send_at=None,
        source_tag=source_tag,
    )
    db.session.add(lead)
    db.session.commit()

    list_ids = cn_config.brevo_list_ids()
    extra_attrs = {}
    if os.getenv("CRO_NURTURE_BREVO_EXTRA_ATTRIBUTES", "").lower() in ("1", "true", "yes"):
        extra_attrs["SITE_URL"] = site_url[:255]
        extra_attrs["CRO_NURTURE_LEAD_ID"] = str(lead.id)
    try:
        ok = upsert_contact(
            email=email,
            first_name=first_name,
            last_name=last_name,
            list_ids=list_ids,
            attributes=extra_attrs or None,
        )
        if not ok:
            current_app.logger.warning("cro_nurture: Brevo upsert failed for %s", email)
    except Exception:
        current_app.logger.exception("cro_nurture: Brevo upsert error for %s", email)
    return lead


def _find_reusable_instant_test_lead(*, email: str, site_url: str) -> CroNurtureLead | None:
    """Latest nurture row for this email+store that was created for instant-test mode."""
    candidates = (
        CroNurtureLead.query.filter_by(email=email, site_url=site_url)
        .order_by(CroNurtureLead.id.desc())
        .limit(8)
        .all()
    )
    for row in candidates:
        if lead_skip_sequence_delays(row):
            return row
    return None


def _reset_instant_test_lead_for_resubmit(lead: CroNurtureLead, *, fresh_payload: dict[str, Any]) -> None:
    """
    Same email+store instant-test resubmit: keep prior scan JSON (e.g. full_report) when present,
    merge new form fields, wipe send history, re-run enrichment + burst.
    """
    old = lead.cro_scan_payload if isinstance(lead.cro_scan_payload, dict) else {}
    merged = {**old, **fresh_payload}
    merged[NURTURE_INSTANT_TEST_KEY] = True
    if "full_report" in old:
        merged["full_report"] = old["full_report"]
    lead.cro_scan_payload = merged
    lead.enrichment_status = "pending"
    lead.enrichment_error = None
    lead.business_profile = None
    lead.fetched_pages = None
    lead.next_step_order = 1
    lead.next_send_at = None
    lead.unsubscribed_at = None
    lead.paused = False
    CroNurtureEmailSend.query.filter_by(lead_id=lead.id).delete()
    db.session.commit()


def create_nurture_lead_from_cro_scan_submit(
    *,
    email: str,
    store_url: str,
    fname: str,
    orders_per_month: str | None,
) -> int | None:
    """Called from /cro-scan/submit-email."""
    if not current_app.config.get("CRO_NURTURE_ENABLED"):
        return None
    site_url = normalize_site_url(store_url)
    email_l = (email or "").strip().lower()
    parts = (fname or "").strip().split(None, 1)
    first_name = parts[0] if parts else None
    last_name = parts[1] if len(parts) > 1 else None

    cro_payload: dict[str, Any] = {"scan_status": "pipeline_started"}
    if orders_per_month:
        cro_payload["orders_per_month"] = orders_per_month
    instant_test = bool(
        current_app.config.get("CRO_NURTURE_TEST_INSTANT_SEQUENCE") and current_app.debug
    )
    if instant_test:
        cro_payload[NURTURE_INSTANT_TEST_KEY] = True

    source_tag = (os.getenv("CRO_NURTURE_DEFAULT_SOURCE_TAG") or "sparksmetrics.com/cro-scan").strip()

    if instant_test:
        reuse = _find_reusable_instant_test_lead(email=email_l, site_url=site_url)
        if reuse:
            reuse.first_name = first_name
            reuse.last_name = last_name
            reuse.source_tag = source_tag
            _reset_instant_test_lead_for_resubmit(reuse, fresh_payload=cro_payload)
            list_ids = cn_config.brevo_list_ids()
            try:
                upsert_contact(
                    email=email_l,
                    first_name=first_name,
                    last_name=last_name,
                    list_ids=list_ids,
                    attributes=None,
                )
            except Exception:
                current_app.logger.exception("cro_nurture: Brevo upsert error on resubmit for %s", email_l)
            return reuse.id

    lead = _persist_nurture_lead(
        email=email_l,
        site_url=site_url,
        first_name=first_name,
        last_name=last_name,
        cro_payload=cro_payload,
        source_tag=source_tag,
    )
    return lead.id if lead else None


def create_nurture_lead_from_api_dict(
    *,
    email: str,
    site_url: str,
    first_name: str | None,
    last_name: str | None,
    cro_payload: dict[str, Any] | None,
    source_tag: str,
) -> CroNurtureLead | None:
    """Used by HTTP /api/ingest after validation (blueprint only mounted when enabled)."""
    if not current_app.config.get("CRO_NURTURE_ENABLED"):
        return None
    return _persist_nurture_lead(
        email=email,
        site_url=site_url,
        first_name=first_name,
        last_name=last_name,
        cro_payload=cro_payload,
        source_tag=source_tag,
    )


def attach_cro_scan_report_to_lead(*, email: str, store_url: str, report: dict[str, Any]) -> None:
    """
    After the scan pipeline finishes, attach report JSON to the latest matching nurture lead
    if enrichment has not run yet.
    """
    if not current_app.config.get("CRO_NURTURE_ENABLED"):
        return
    email_l = (email or "").strip().lower()
    if not email_l:
        return
    try:
        nu = normalize_site_url(store_url)
    except Exception:
        nu = (store_url or "").strip()

    lead = (
        CroNurtureLead.query.filter_by(email=email_l, site_url=nu)
        .filter(CroNurtureLead.enrichment_status == "pending")
        .order_by(CroNurtureLead.id.desc())
        .first()
    )
    if not lead:
        lead = CroNurtureLead.query.filter_by(email=email_l).order_by(CroNurtureLead.id.desc()).first()
    if not lead:
        current_app.logger.warning(
            "cro_nurture: no nurture lead to attach scan (email=%s site=%s). "
            "Check CRO_NURTURE_ENABLED and that submit-email created a lead for this email.",
            email_l,
            nu,
        )
        return

    slim = _strip_heavy_report(report)
    base = lead.cro_scan_payload if isinstance(lead.cro_scan_payload, dict) else {}
    merged = {**base, "full_report": slim, "scan_status": "complete"}
    lead.cro_scan_payload = merged
    # Re-build profile with full scan in payload before first nurture (enrich may have run earlier without it).
    if lead.enrichment_status in ("ok", "failed"):
        lead.enrichment_status = "pending"
        lead.business_profile = None
        lead.fetched_pages = None
        lead.enrichment_error = None
    # Prod: first nurture email is scheduled from scan attach time (+ step 1 delay, default 2h).
    # Instant-test leads: cron must not send; background test thread runs the burst after a short wait.
    if lead_skip_sequence_delays(lead):
        lead.next_send_at = None
    elif lead.next_step_order == 1 and not step1_email_already_sent(lead):
        # Prod: step 1 delay from DB (e.g. 2h). Local DEBUG: default 0s so post-scan cron kick can send #1 immediately.
        # Set CRO_NURTURE_LOCAL_FIRST_EMAIL_SECONDS=120 (or 7200) to simulate prod timing locally.
        if current_app.debug and not lead_skip_sequence_delays(lead):
            raw = os.getenv("CRO_NURTURE_LOCAL_FIRST_EMAIL_SECONDS", "0").strip()
            delay = int(raw) if raw.isdigit() else first_send_delay_seconds_from_sequence(lead)
        else:
            delay = first_send_delay_seconds_from_sequence(lead)
        lead.next_send_at = datetime.utcnow() + timedelta(seconds=delay)
    db.session.commit()
    current_app.logger.info(
        "cro_nurture: attached scan to lead id=%s enrich=%s next_send_at=%s",
        lead.id,
        lead.enrichment_status,
        lead.next_send_at,
    )
