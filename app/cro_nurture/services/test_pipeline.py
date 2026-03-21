"""Dev-only: wait for scan JSON, pause, re-enrich, then burst full sequence (CRO_NURTURE_TEST_INSTANT_SEQUENCE)."""

from __future__ import annotations

import time

from app.models import db
from app.cro_nurture.lead_flags import lead_skip_sequence_delays
from app.cro_nurture.models import CroNurtureLead
from app.cro_nurture.scan_schedule import lead_has_attached_cro_scan
from app.cro_nurture.services import config as cn_config
from app.cro_nurture.services.dispatch import run_burst_dispatch_for_lead
from app.cro_nurture.services.enrichment import enrich_pending_lead_by_id


def run_instant_test_sequence_after_submit(lead_id: int) -> dict:
    """
    1) Poll until cro_scan_payload.full_report exists (scan pipeline finished).
    2) Wait CRO_NURTURE_TEST_WAIT_BEFORE_NURTURE_SECONDS (default 2 minutes).
    3) Re-run enrichment so business_profile uses the full scan.
    4) Send all sequence steps back-to-back (zero between-step delays for this lead).
    """
    lead = CroNurtureLead.query.get(lead_id)
    if not lead or not lead_skip_sequence_delays(lead):
        return {"skipped": True, "reason": "not_instant_test_lead"}

    max_wait = cn_config.test_wait_for_scan_report_max_seconds()
    saw_report = False
    for _ in range(max_wait):
        db.session.expire_all()
        lead = CroNurtureLead.query.get(lead_id)
        if not lead:
            return {"error": "lead_gone"}
        if lead_has_attached_cro_scan(lead):
            saw_report = True
            break
        time.sleep(1)

    wait_after = cn_config.test_wait_before_nurture_burst_seconds()
    time.sleep(wait_after)

    lead = CroNurtureLead.query.get(lead_id)
    if not lead:
        return {"error": "lead_gone_after_wait"}

    # Rebuild profile with full scan in payload (cron may have enriched before full_report existed).
    if lead.enrichment_status != "pending":
        lead.enrichment_status = "pending"
        lead.business_profile = None
        lead.fetched_pages = None
        lead.enrichment_error = None
        db.session.commit()

    enrich_pending_lead_by_id(lead_id)

    for _ in range(120):
        db.session.expire_all()
        lead = CroNurtureLead.query.get(lead_id)
        if not lead:
            return {"error": "lead_gone"}
        if lead.enrichment_status in ("ok", "failed"):
            break
        time.sleep(0.25)
    else:
        return {"error": "enrichment_timeout"}

    burst = run_burst_dispatch_for_lead(lead_id, max_steps=25)
    return {
        "saw_scan_report": saw_report,
        "enrichment": lead.enrichment_status,
        **burst,
    }
